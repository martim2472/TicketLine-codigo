"""
Ticketline — Plataforma de suporte técnico (PAP GPSI)
Ficheiros principais:
  app.py      → rotas e lógica da aplicação
  database.py → ligação SQLite e criação das tabelas
  utils.py    → funções auxiliares (gráficos, datas, ficheiros)
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, session, jsonify, Response)
from database import get_db, init_db, criar_admin_se_nao_existir
from utils import (allowed, tempo_desde, is_online,
                   chart_por_cat, chart_por_estado, chart_por_prio)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
from io import BytesIO
from xhtml2pdf import pisa
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import secrets
import uuid
import os

app = Flask(__name__)
app.secret_key = "ticketline_secret_2025"

UPLOAD_FOLDER         = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
UPLOAD_TICKETS_FOLDER = os.path.join(UPLOAD_FOLDER, 'tickets')
ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_ALL = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'zip'}
os.makedirs(UPLOAD_FOLDER,         exist_ok=True)
os.makedirs(UPLOAD_TICKETS_FOLDER, exist_ok=True)

init_db()
criar_admin_se_nao_existir()

# ─── Email ────────────────────────────────────────────────────────────────────
EMAIL_REMETENTE    = "supporticketline@gmail.com"
EMAIL_APP_PASSWORD = "nfws svyz pmvk cioa"   # App Password Gmail (16 chars)

def _enviar_email_smtp(para, assunto, html):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = f"Ticketline <{EMAIL_REMETENTE}>"
        msg["To"]      = para
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as s:
            s.ehlo(); s.starttls()
            s.login(EMAIL_REMETENTE, EMAIL_APP_PASSWORD)
            s.sendmail(EMAIL_REMETENTE, para, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Erro ao enviar: {e}")
        return False

def enviar_email(para, assunto, html):
    if "COLOCA_AQUI" in EMAIL_APP_PASSWORD:
        print(f"[EMAIL-DEBUG] Para:{para}  Assunto:{assunto}")
        return False
    return _enviar_email_smtp(para, assunto, html)

TEMPLATE_EMAIL = """
<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:580px;margin:0 auto;background:#120e1a;border-radius:18px;overflow:hidden;border:1px solid rgba(255,255,255,0.1);">
  <div style="background:linear-gradient(135deg,#ff758c,#a64bf4);padding:36px 32px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:1.6rem;letter-spacing:1px;">🎟️ Ticketline</h1>
    <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:.9rem;">Suporte que une Pessoas e Empresas</p>
  </div>
  <div style="padding:32px;">{CORPO}</div>
  <div style="padding:18px 32px;text-align:center;border-top:1px solid rgba(255,255,255,0.08);color:#7a7090;font-size:.78rem;">
    Ticketline &bull; EPBJC &bull; supporticketline@gmail.com &bull; 937 458 729
  </div>
</div>
"""

def email_boas_vindas(nome, email):
    corpo = TEMPLATE_EMAIL.replace("{CORPO}", f"""
      <h2 style="color:#ff7eb3;margin-top:0;">Bem-vindo, {nome}! 🎉</h2>
      <p style="color:#c9c5d8;line-height:1.7;">A tua conta foi criada com sucesso. Já podes iniciar sessão e começar a usar a plataforma.</p>
      <p style="color:#c9c5d8;line-height:1.7;">📞 <strong>937 458 729</strong><br>✉️ <strong>supporticketline@gmail.com</strong></p>
      <a href="http://localhost:5000/login" style="display:inline-block;margin-top:20px;padding:13px 28px;background:linear-gradient(45deg,#ff758c,#ff7eb3);color:#fff;border-radius:12px;text-decoration:none;font-weight:700;font-size:.95rem;">Entrar na Minha Conta →</a>
    """)
    enviar_email(email, "Bem-vindo ao Ticketline! 🎉", corpo)

def email_reset(email, nome, token):
    link  = f"http://localhost:5000/redefinir-password/{token}"
    print(f"[RESET-LINK] {link}")
    corpo = TEMPLATE_EMAIL.replace("{CORPO}", f"""
      <h2 style="color:#a64bf4;margin-top:0;">Recuperação de Password 🔑</h2>
      <p style="color:#c9c5d8;line-height:1.7;">Olá <strong style="color:#fff;">{nome}</strong>,</p>
      <p style="color:#c9c5d8;line-height:1.7;">Clica no botão abaixo para redefinir a tua password. O link é válido durante <strong>1 hora</strong>.</p>
      <a href="{link}" style="display:inline-block;margin-top:20px;padding:13px 28px;background:linear-gradient(45deg,#a64bf4,#c471ed);color:#fff;border-radius:12px;text-decoration:none;font-weight:700;font-size:.95rem;">Redefinir Password →</a>
      <p style="color:#7a7090;font-size:.8rem;margin-top:20px;">Ou copia: <span style="color:#a64bf4;">{link}</span></p>
      <p style="color:#7a7090;font-size:.8rem;">Se não pediste esta alteração, ignora este email.</p>
    """)
    return enviar_email(email, "Recuperação de Password — Ticketline", corpo)

# ─── Variáveis globais nos templates ──────────────────────────────────────────
@app.context_processor
def inject_globals():
    nao_lidas = 0
    if "id" in session and session.get("tipo") in ("helpdesk", "admin"):
        try:
            db = get_db()
            nao_lidas = db.execute(
                "SELECT COUNT(*) FROM mensagem_interna WHERE destinatario_id=? AND lida=0",
                (session["id"],)
            ).fetchone()[0]
            db.close()
        except Exception:
            pass
    return {"nao_lidas_msg": nao_lidas}

app.jinja_env.globals.update(tempo_desde=tempo_desde, is_online=is_online)

@app.before_request
def atualizar_acesso():
    if "id" in session:
        try:
            db = get_db()
            db.execute("UPDATE utilizador SET ultimo_acesso=datetime('now') WHERE id=?", (session["id"],))
            db.commit()
            db.close()
        except Exception:
            pass

# ─── Decoradores de acesso ────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "id" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

def cliente_required(f):
    @wraps(f)
    def w(*a, **k):
        if "id" not in session or session.get("tipo") != "cliente":
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

def helpdesk_required(f):
    @wraps(f)
    def w(*a, **k):
        if "id" not in session or session.get("tipo") != "helpdesk":
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if "id" not in session or session.get("tipo") != "admin":
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

def staff_required(f):
    @wraps(f)
    def w(*a, **k):
        if "id" not in session or session.get("tipo") not in ("helpdesk", "admin"):
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

# ═══════════════════════════════════════════════════════════════════════════════
# ROTAS PÚBLICAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    if request.method == "POST":
        nome     = request.form.get("nome", "").strip()
        email    = request.form.get("email", "").strip()
        assunto  = request.form.get("assunto", "").strip()
        mensagem = request.form.get("mensagem", "").strip()

        if not nome or not email or not assunto or not mensagem:
            flash("Preenche todos os campos.", "erro")
            return redirect(url_for("contacto"))

        db = get_db()
        db.execute(
            "INSERT INTO mensagem_contacto (nome, email, assunto, mensagem) VALUES (?, ?, ?, ?)",
            (nome, email, assunto, mensagem),
        )
        db.commit()
        db.close()

        corpo = TEMPLATE_EMAIL.replace("{CORPO}", f"""
          <h2 style="color:#ff7eb3;margin-top:0;">Nova mensagem de contacto</h2>
          <p style="color:#c9c5d8;"><strong>{nome}</strong> &lt;{email}&gt;</p>
          <p style="color:#c9c5d8;"><strong>Assunto:</strong> {assunto}</p>
          <p style="color:#c9c5d8;line-height:1.7;">{mensagem}</p>
        """)
        enviar_email(EMAIL_REMETENTE, f"Contacto Ticketline: {assunto}", corpo)

        flash("Mensagem enviada com sucesso! Entraremos em contacto em breve.", "sucesso")
        return redirect(url_for("contacto"))

    return render_template("contacto.html")

@app.route("/tipos-servico")
def tipos_servico():
    return render_template("tipos_servico.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/registo", methods=["GET", "POST"])
def registo():
    if request.method == "POST":
        nome     = request.form.get("nome", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        tipo     = request.form.get("tipo", "cliente")
        if tipo not in ("cliente", "helpdesk"):
            tipo = "cliente"
        empresa = request.form.get("empresa", "").strip() if tipo == "cliente" else ""
        if not nome or not email or not password:
            flash("Preenche todos os campos.", "erro")
            return redirect(url_for("registo"))
        db = get_db()
        if db.execute("SELECT id FROM utilizador WHERE email=?", (email,)).fetchone():
            db.close()
            flash("Email já registado.", "erro")
            return redirect(url_for("registo"))
        db.execute(
            "INSERT INTO utilizador (nome,email,password,tipo,empresa) VALUES (?,?,?,?,?)",
            (nome, email, generate_password_hash(password), tipo, empresa)
        )
        db.commit(); db.close()
        email_boas_vindas(nome, email)
        flash("Conta criada com sucesso! Bem-vindo ao Ticketline 🎉", "sucesso")
        return redirect(url_for("login"))
    return render_template("registo.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        pw    = request.form.get("password", "")
        db   = get_db()
        user = db.execute("SELECT * FROM utilizador WHERE email=?", (email,)).fetchone()
        db.close()
        if user and check_password_hash(user["password"], pw):
            session.update(
                id=user["id"], nome=user["nome"], tipo=user["tipo"],
                empresa=user["empresa"], foto_perfil=user["foto_perfil"]
            )
            destinos = {"helpdesk": "dashboard_helpdesk", "admin": "dashboard_admin"}
            return redirect(url_for(destinos.get(user["tipo"], "dashboard_cliente")))
        flash("Email ou password incorretos.", "erro")
    return render_template("login.html")

# ─── Recuperação de password ──────────────────────────────────────────────────
@app.route("/recuperar-password", methods=["GET", "POST"])
def recuperar_password():
    link_reset = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        db    = get_db()
        user  = db.execute("SELECT * FROM utilizador WHERE email=?", (email,)).fetchone()
        if user:
            token     = secrets.token_urlsafe(40)
            expira_em = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            db.execute("DELETE FROM password_reset_token WHERE utilizador_id=?", (user["id"],))
            db.execute(
                "INSERT INTO password_reset_token (utilizador_id,token,expira_em) VALUES (?,?,?)",
                (user["id"], token, expira_em)
            )
            db.commit()
            link_reset = url_for("redefinir_password", token=token, _external=True)
            enviado = email_reset(user["email"], user["nome"], token)
            if enviado:
                flash("Email de recuperação enviado! Verifica a tua caixa de correio.", "sucesso")
            else:
                flash("Usa o link abaixo para redefinir a password (válido 1 hora):", "aviso")
        else:
            flash("Se esse email estiver registado, receberás instruções de recuperação.", "sucesso")
        db.close()
    return render_template("recuperar_password.html", link_reset=link_reset)

@app.route("/redefinir-password/<token>", methods=["GET", "POST"])
def redefinir_password(token):
    db  = get_db()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        "SELECT * FROM password_reset_token WHERE token=? AND expira_em>? AND usado=0",
        (token, now)
    ).fetchone()
    if not row:
        db.close()
        flash("Link inválido ou expirado.", "erro")
        return redirect(url_for("recuperar_password"))
    if request.method == "POST":
        nova = request.form.get("password", "")
        conf = request.form.get("confirma", "")
        if len(nova) < 6:
            flash("Mínimo 6 caracteres.", "erro")
            return redirect(url_for("redefinir_password", token=token))
        if nova != conf:
            flash("Passwords não coincidem.", "erro")
            return redirect(url_for("redefinir_password", token=token))
        db.execute("UPDATE utilizador SET password=? WHERE id=?",
                   (generate_password_hash(nova), row["utilizador_id"]))
        db.execute("UPDATE password_reset_token SET usado=1 WHERE token=?", (token,))
        db.commit(); db.close()
        flash("Password alterada! Já podes fazer login.", "sucesso")
        return redirect(url_for("login"))
    db.close()
    return render_template("redefinir_password.html", token=token)

# ═══════════════════════════════════════════════════════════════════════════════
# PERFIL
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/perfil/<int:id>")
@login_required
def ver_perfil(id):
    db   = get_db()
    user = db.execute("SELECT * FROM utilizador WHERE id=?", (id,)).fetchone()
    if not user:
        db.close()
        flash("Utilizador não encontrado.", "erro")
        return redirect(url_for("index"))
    tc  = db.execute("SELECT COUNT(*) FROM ticket WHERE cliente_id=?", (id,)).fetchone()[0]
    tr  = db.execute("SELECT COUNT(*) FROM ticket WHERE agente_id=? AND estado='fechado'", (id,)).fetchone()[0]
    tea = db.execute("SELECT COUNT(*) FROM ticket WHERE agente_id=? AND estado='em_analise'", (id,)).fetchone()[0]
    avg = db.execute("SELECT AVG(estrelas) as m, COUNT(*) as t FROM avaliacao WHERE agente_id=?", (id,)).fetchone()
    media_av = round(avg["m"] or 0, 1)
    total_av = avg["t"] or 0
    avaliacoes = []
    if user["tipo"] in ("helpdesk", "admin"):
        avaliacoes = db.execute(
            "SELECT a.*,u.nome AS cliente_nome FROM avaliacao a "
            "JOIN utilizador u ON a.cliente_id=u.id WHERE a.agente_id=? ORDER BY a.id DESC LIMIT 5",
            (id,)
        ).fetchall()
    pode_mensagem = (
        session.get("tipo") in ("helpdesk", "admin") and
        user["tipo"] in ("helpdesk", "admin") and
        user["id"] != session.get("id")
    )
    db.close()
    return render_template("perfil.html",
        user=user, tickets_criados=tc, tickets_resolvidos=tr,
        tickets_em_analise=tea, media_avaliacao=media_av,
        total_avaliacao=total_av, avaliacoes=avaliacoes,
        proprio=(id == session.get("id")), pode_mensagem=pode_mensagem
    )

@app.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def editar_perfil():
    db   = get_db()
    user = db.execute("SELECT * FROM utilizador WHERE id=?", (session["id"],)).fetchone()
    if request.method == "POST":
        nome    = request.form.get("nome", "").strip()
        empresa = request.form.get("empresa", "").strip()
        if not nome:
            flash("Nome vazio.", "erro"); db.close()
            return redirect(url_for("editar_perfil"))
        foto_fn = user["foto_perfil"]
        foto    = request.files.get("foto")
        if foto and foto.filename and allowed(foto.filename, ALLOWED_IMG):
            if foto_fn:
                old = os.path.join(UPLOAD_FOLDER, foto_fn)
                if os.path.exists(old): os.remove(old)
            ext    = foto.filename.rsplit('.', 1)[1].lower()
            foto_fn = f"{uuid.uuid4().hex}.{ext}"
            foto.save(os.path.join(UPLOAD_FOLDER, foto_fn))
        db.execute("UPDATE utilizador SET nome=?,empresa=?,foto_perfil=? WHERE id=?",
                   (nome, empresa, foto_fn, session["id"]))
        db.commit(); db.close()
        session.update(nome=nome, empresa=empresa, foto_perfil=foto_fn)
        flash("Perfil atualizado!", "sucesso")
        return redirect(url_for("ver_perfil", id=session["id"]))
    db.close()
    return render_template("editar_perfil.html", user=user)

# ─── Admin editar utilizador ──────────────────────────────────────────────────
@app.route("/admin/utilizador/<int:id>/editar", methods=["GET", "POST"])
@admin_required
def admin_editar_utilizador(id):
    db   = get_db()
    user = db.execute("SELECT * FROM utilizador WHERE id=?", (id,)).fetchone()
    if not user:
        db.close()
        flash("Utilizador não encontrado.", "erro")
        return redirect(url_for("utilizadores"))
    if request.method == "POST":
        nome    = request.form.get("nome", "").strip()
        empresa = request.form.get("empresa", "").strip()
        if not nome:
            flash("Nome vazio.", "erro"); db.close()
            return redirect(url_for("admin_editar_utilizador", id=id))
        db.execute("UPDATE utilizador SET nome=?,empresa=? WHERE id=?", (nome, empresa, id))
        db.commit(); db.close()
        flash(f"Utilizador {nome} atualizado.", "sucesso")
        return redirect(url_for("ver_perfil", id=id))
    db.close()
    return render_template("admin_editar_utilizador.html", user=user)

# ═══════════════════════════════════════════════════════════════════════════════
# UTILIZADORES (admin only)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/utilizadores")
@admin_required
def utilizadores():
    db = get_db()
    clientes = db.execute(
        "SELECT * FROM utilizador WHERE tipo='cliente' ORDER BY nome"
    ).fetchall()
    agentes = db.execute(
        """SELECT u.*,
                  ROUND(AVG(a.estrelas),1) as media_av,
                  COUNT(a.id) as total_av
           FROM utilizador u
           LEFT JOIN avaliacao a ON a.agente_id=u.id
           WHERE u.tipo IN ('helpdesk','admin')
           GROUP BY u.id ORDER BY u.nome"""
    ).fetchall()
    db.close()
    return render_template("utilizadores.html", clientes=clientes, agentes=agentes)

# ═══════════════════════════════════════════════════════════════════════════════
# ESTATÍSTICAS (todos os utilizadores logados)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/estatisticas")
@login_required
def estatisticas():
    db = get_db()
    mes_atual = datetime.now().strftime("%Y-%m")
    total_tickets = db.execute("SELECT COUNT(*) FROM ticket").fetchone()[0]
    abertos  = db.execute("SELECT COUNT(*) FROM ticket WHERE estado='aberto'").fetchone()[0]
    analise  = db.execute("SELECT COUNT(*) FROM ticket WHERE estado='em_analise'").fetchone()[0]
    fechados = db.execute("SELECT COUNT(*) FROM ticket WHERE estado='fechado'").fetchone()[0]
    este_mes_c = db.execute(
        "SELECT COUNT(*) FROM ticket WHERE strftime('%Y-%m', criado_em)=?", (mes_atual,)
    ).fetchone()[0]
    este_mes_r = db.execute(
        "SELECT COUNT(*) FROM ticket WHERE estado='fechado' AND strftime('%Y-%m', fechado_em)=?",
        (mes_atual,)
    ).fetchone()[0]
    por_cat  = db.execute("SELECT categoria,COUNT(*) as n FROM ticket GROUP BY categoria ORDER BY n DESC").fetchall()
    por_prio = db.execute("SELECT prioridade,COUNT(*) as n FROM ticket GROUP BY prioridade ORDER BY n DESC").fetchall()
    top_agentes = db.execute(
        """SELECT u.nome,COUNT(DISTINCT t.id) as n,ROUND(AVG(av.estrelas),1) as media
           FROM ticket t
           JOIN utilizador u ON t.agente_id=u.id
           LEFT JOIN avaliacao av ON av.agente_id=u.id
           WHERE t.estado='fechado'
           GROUP BY u.id ORDER BY n DESC LIMIT 5"""
    ).fetchall()
    cat_top = db.execute(
        "SELECT categoria FROM ticket GROUP BY categoria ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    db.close()
    return render_template("estatisticas.html",
        total_tickets=total_tickets, abertos=abertos, analise=analise, fechados=fechados,
        este_mes_c=este_mes_c, este_mes_r=este_mes_r,
        por_cat=por_cat, por_prio=por_prio, top_agentes=top_agentes,
        cat_top=cat_top["categoria"] if cat_top else "—",
        chart_data={"cat": chart_por_cat(por_cat), "prio": chart_por_prio(por_prio)},
    )

# ═══════════════════════════════════════════════════════════════════════════════
# MENSAGENS INTERNAS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/mensagens")
@staff_required
def mensagens():
    db = get_db()
    recebidas = db.execute(
        """SELECT m.*,u.nome AS remetente_nome,u.foto_perfil AS remetente_foto
           FROM mensagem_interna m JOIN utilizador u ON m.remetente_id=u.id
           WHERE m.destinatario_id=? ORDER BY m.criado_em DESC""",
        (session["id"],)
    ).fetchall()
    enviadas = db.execute(
        """SELECT m.*,u.nome AS destinatario_nome,u.foto_perfil AS destinatario_foto
           FROM mensagem_interna m JOIN utilizador u ON m.destinatario_id=u.id
           WHERE m.remetente_id=? ORDER BY m.criado_em DESC""",
        (session["id"],)
    ).fetchall()
    db.execute("UPDATE mensagem_interna SET lida=1 WHERE destinatario_id=?", (session["id"],))
    db.commit(); db.close()
    return render_template("mensagens.html", recebidas=recebidas, enviadas=enviadas)

@app.route("/mensagens/nova", methods=["GET", "POST"])
@staff_required
def nova_mensagem():
    db = get_db()
    destinatarios = db.execute(
        "SELECT id,nome,tipo FROM utilizador WHERE tipo IN ('helpdesk','admin') AND id!=? ORDER BY nome",
        (session["id"],)
    ).fetchall()
    para_id = request.args.get("para", type=int)
    if request.method == "POST":
        dest_id = int(request.form.get("destinatario_id", 0))
        assunto = request.form.get("assunto", "Sem assunto").strip()
        corpo   = request.form.get("corpo", "").strip()
        if not corpo or not dest_id:
            flash("Preenche todos os campos.", "erro")
        else:
            db.execute(
                "INSERT INTO mensagem_interna (remetente_id,destinatario_id,assunto,corpo) VALUES (?,?,?,?)",
                (session["id"], dest_id, assunto, corpo)
            )
            db.commit()
            flash("Mensagem enviada!", "sucesso")
            db.close()
            return redirect(url_for("mensagens"))
    db.close()
    return render_template("nova_mensagem.html", destinatarios=destinatarios, para_id=para_id)

# ═══════════════════════════════════════════════════════════════════════════════
# AVALIAÇÕES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/ticket/<int:id>/avaliar", methods=["GET", "POST"])
@cliente_required
def avaliar_ticket(id):
    db = get_db()
    t  = db.execute("SELECT * FROM ticket WHERE id=? AND cliente_id=?", (id, session["id"])).fetchone()
    if not t or t["estado"] != "fechado" or not t["agente_id"]:
        db.close(); flash("Não é possível avaliar.", "erro")
        return redirect(url_for("dashboard_cliente"))
    if db.execute("SELECT id FROM avaliacao WHERE ticket_id=?", (id,)).fetchone():
        db.close(); flash("Já avaliaste este ticket.", "erro")
        return redirect(url_for("ver_ticket", id=id))
    if request.method == "POST":
        estrelas   = max(1, min(5, int(request.form.get("estrelas", 3))))
        comentario = request.form.get("comentario", "").strip()
        db.execute(
            "INSERT INTO avaliacao (ticket_id,cliente_id,agente_id,estrelas,comentario) VALUES (?,?,?,?,?)",
            (id, session["id"], t["agente_id"], estrelas, comentario or None)
        )
        db.commit(); db.close()
        flash("Avaliação enviada! Obrigado.", "sucesso")
        return redirect(url_for("ver_ticket", id=id))
    agente = db.execute("SELECT nome FROM utilizador WHERE id=?", (t["agente_id"],)).fetchone()
    db.close()
    return render_template("avaliar.html", ticket=t, agente=agente)

# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARDS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard/cliente")
@cliente_required
def dashboard_cliente():
    db      = get_db()
    tickets = db.execute(
        "SELECT * FROM ticket WHERE cliente_id=? ORDER BY id DESC", (session["id"],)
    ).fetchall()
    por_cat = db.execute(
        "SELECT categoria,COUNT(*) as n FROM ticket WHERE cliente_id=? GROUP BY categoria", (session["id"],)
    ).fetchall()
    este_mes = db.execute(
        "SELECT COUNT(*) FROM ticket WHERE cliente_id=? AND strftime('%Y-%m', criado_em)=?",
        (session["id"], datetime.now().strftime("%Y-%m"))
    ).fetchone()[0]
    db.close()
    total   = len(tickets)
    abertos  = sum(1 for t in tickets if t["estado"] == "aberto")
    analise  = sum(1 for t in tickets if t["estado"] == "em_analise")
    fechados = sum(1 for t in tickets if t["estado"] == "fechado")
    return render_template("dashboard_cliente.html",
        tickets=tickets, total=total, abertos=abertos,
        analise=analise, fechados=fechados, este_mes=este_mes, por_cat=por_cat,
        chart_data=chart_por_cat(por_cat),
    )

@app.route("/ticket/criar", methods=["GET", "POST"])
@cliente_required
def criar_ticket():
    if request.method == "POST":
        titulo   = request.form.get("titulo", "").strip()
        descricao = request.form.get("descricao", "").strip()
        if not titulo or not descricao:
            flash("Preenche título e descrição.", "erro")
            return redirect(url_for("criar_ticket"))
        db  = get_db()
        cur = db.execute(
            "INSERT INTO ticket (titulo,descricao,categoria,prioridade,cliente_id) VALUES (?,?,?,?,?)",
            (titulo, descricao, request.form.get("categoria", "geral"),
             request.form.get("prioridade", "normal"), session["id"])
        )
        tid = cur.lastrowid
        for f in request.files.getlist("anexos"):
            if f and f.filename and allowed(f.filename, ALLOWED_ALL):
                ext = f.filename.rsplit('.', 1)[1].lower()
                fn  = f"{uuid.uuid4().hex}.{ext}"
                f.save(os.path.join(UPLOAD_TICKETS_FOLDER, fn))
                db.execute(
                    "INSERT INTO anexo_ticket (ticket_id,utilizador_id,filename) VALUES (?,?,?)",
                    (tid, session["id"], fn)
                )
        db.commit(); db.close()
        flash("Ticket criado com sucesso!", "sucesso")
        return redirect(url_for("dashboard_cliente"))
    return render_template("criar_ticket.html")

@app.route("/dashboard/helpdesk")
@helpdesk_required
def dashboard_helpdesk():
    db      = get_db()
    tickets = db.execute(
        "SELECT t.*,u.nome AS cliente_nome,u.empresa FROM ticket t "
        "JOIN utilizador u ON t.cliente_id=u.id ORDER BY t.id DESC"
    ).fetchall()
    por_cat = db.execute("SELECT categoria,COUNT(*) as n FROM ticket GROUP BY categoria").fetchall()
    top_agentes = db.execute(
        "SELECT u.nome,COUNT(*) as r FROM ticket t "
        "JOIN utilizador u ON t.agente_id=u.id WHERE t.estado='fechado' "
        "GROUP BY u.id ORDER BY r DESC LIMIT 5"
    ).fetchall()
    db.close()
    total   = len(tickets)
    abertos  = sum(1 for t in tickets if t["estado"] == "aberto")
    analise  = sum(1 for t in tickets if t["estado"] == "em_analise")
    fechados = sum(1 for t in tickets if t["estado"] == "fechado")
    return render_template("dashboard_helpdesk.html",
        tickets=tickets, total=total, abertos=abertos,
        analise=analise, fechados=fechados, por_cat=por_cat, top_agentes=top_agentes
    )

@app.route("/helpdesk/tickets")
@staff_required
def tickets_helpdesk():
    db = get_db()
    tickets = db.execute(
        "SELECT t.*,u.nome AS cliente_nome,u.empresa FROM ticket t "
        "JOIN utilizador u ON t.cliente_id=u.id ORDER BY t.id DESC"
    ).fetchall()
    db.close()
    return render_template("tickets.html", tickets=tickets)

@app.route("/dashboard/admin")
@admin_required
def dashboard_admin():
    db = get_db()
    mes_atual = datetime.now().strftime("%Y-%m")
    total_users    = db.execute("SELECT COUNT(*) FROM utilizador WHERE tipo!='admin'").fetchone()[0]
    total_clientes = db.execute("SELECT COUNT(*) FROM utilizador WHERE tipo='cliente'").fetchone()[0]
    total_agentes  = db.execute("SELECT COUNT(*) FROM utilizador WHERE tipo='helpdesk'").fetchone()[0]
    total_tickets  = db.execute("SELECT COUNT(*) FROM ticket").fetchone()[0]
    por_cat   = db.execute("SELECT categoria,COUNT(*) as n FROM ticket GROUP BY categoria ORDER BY n DESC").fetchall()
    por_estado = db.execute("SELECT estado,COUNT(*) as n FROM ticket GROUP BY estado").fetchall()
    este_mes_c = db.execute(
        "SELECT COUNT(*) FROM ticket WHERE strftime('%Y-%m', criado_em)=?", (mes_atual,)
    ).fetchone()[0]
    este_mes_r = db.execute(
        "SELECT COUNT(*) FROM ticket WHERE estado='fechado' AND strftime('%Y-%m', fechado_em)=?",
        (mes_atual,)
    ).fetchone()[0]
    cat_top = db.execute("SELECT categoria,COUNT(*) as n FROM ticket GROUP BY categoria ORDER BY n DESC LIMIT 1").fetchone()
    # SQLite: sem NULLS LAST — usar CASE
    agentes_stats = db.execute(
        """SELECT u.id,u.nome,u.foto_perfil,u.ultimo_acesso,
                  COUNT(DISTINCT t.id) as tickets_resolvidos,
                  ROUND(AVG(a.estrelas),1) as media_av,
                  COUNT(DISTINCT a.id) as total_av
           FROM utilizador u
           LEFT JOIN ticket t ON t.agente_id=u.id AND t.estado='fechado'
           LEFT JOIN avaliacao a ON a.agente_id=u.id
           WHERE u.tipo='helpdesk'
           GROUP BY u.id
           ORDER BY CASE WHEN AVG(a.estrelas) IS NULL THEN 1 ELSE 0 END,
                    AVG(a.estrelas) DESC"""
    ).fetchall()
    ultimos_tickets = db.execute(
        "SELECT t.*,u.nome AS cliente_nome FROM ticket t "
        "JOIN utilizador u ON t.cliente_id=u.id ORDER BY t.id DESC LIMIT 10"
    ).fetchall()
    ultimos_contactos = db.execute(
        "SELECT * FROM mensagem_contacto ORDER BY id DESC LIMIT 5"
    ).fetchall()
    db.close()
    return render_template("dashboard_admin.html",
        total_users=total_users, total_clientes=total_clientes, total_agentes=total_agentes,
        total_tickets=total_tickets, tickets_abertos=este_mes_c, tickets_fechados=este_mes_r,
        por_cat=por_cat, por_estado=por_estado,
        este_mes_c=este_mes_c, este_mes_r=este_mes_r,
        cat_top=cat_top, agentes_stats=agentes_stats, ultimos_tickets=ultimos_tickets,
        ultimos_contactos=ultimos_contactos,
        chart_data={"cat": chart_por_cat(por_cat), "estado": chart_por_estado(por_estado)},
    )

# ═══════════════════════════════════════════════════════════════════════════════
# TICKETS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/ticket/<int:id>")
@login_required
def ver_ticket(id):
    db = get_db()
    ticket = db.execute(
        "SELECT t.*,u.nome AS cliente_nome,u.empresa FROM ticket t "
        "JOIN utilizador u ON t.cliente_id=u.id WHERE t.id=?", (id,)
    ).fetchone()
    if not ticket:
        db.close(); flash("Ticket não encontrado.", "erro")
        return redirect(url_for("index"))
    if session.get("tipo") == "cliente" and ticket["cliente_id"] != session["id"]:
        db.close(); flash("Sem permissão.", "erro")
        return redirect(url_for("dashboard_cliente"))
    respostas = db.execute(
        "SELECT r.*,u.nome,u.tipo AS utilizador_tipo,u.foto_perfil "
        "FROM resposta_ticket r JOIN utilizador u ON r.utilizador_id=u.id "
        "WHERE r.ticket_id=? ORDER BY r.id", (id,)
    ).fetchall()
    anexos = db.execute(
        "SELECT * FROM anexo_ticket WHERE ticket_id=? AND resposta_id IS NULL ORDER BY id", (id,)
    ).fetchall()
    anexos_resp = {
        r["id"]: db.execute("SELECT * FROM anexo_ticket WHERE resposta_id=?", (r["id"],)).fetchall()
        for r in respostas
    }
    ja_avaliou = db.execute("SELECT id FROM avaliacao WHERE ticket_id=?", (id,)).fetchone()
    db.close()
    return render_template("ticket.html",
        ticket=ticket, respostas=respostas,
        anexos=anexos, anexos_resposta=anexos_resp, ja_avaliou=ja_avaliou
    )

@app.route("/ticket/<int:id>/responder", methods=["POST"])
@staff_required
def responder_ticket(id):
    mensagem = request.form.get("mensagem", "").strip()
    if not mensagem:
        flash("Mensagem vazia.", "erro")
        return redirect(url_for("ver_ticket", id=id))
    db     = get_db()
    ticket = db.execute("SELECT * FROM ticket WHERE id=?", (id,)).fetchone()
    if not ticket:
        db.close(); return redirect(url_for("index"))
    cur = db.execute(
        "INSERT INTO resposta_ticket (ticket_id,utilizador_id,mensagem) VALUES (?,?,?)",
        (id, session["id"], mensagem)
    )
    rid = cur.lastrowid
    if ticket["estado"] == "aberto":
        db.execute("UPDATE ticket SET agente_id=?,estado='em_analise' WHERE id=?", (session["id"], id))
    for f in request.files.getlist("anexos"):
        if f and f.filename and allowed(f.filename, ALLOWED_ALL):
            ext = f.filename.rsplit('.', 1)[1].lower()
            fn  = f"{uuid.uuid4().hex}.{ext}"
            f.save(os.path.join(UPLOAD_TICKETS_FOLDER, fn))
            db.execute(
                "INSERT INTO anexo_ticket (ticket_id,resposta_id,utilizador_id,filename) VALUES (?,?,?,?)",
                (id, rid, session["id"], fn)
            )
    db.commit(); db.close()
    return redirect(url_for("ver_ticket", id=id))

@app.route("/ticket/<int:id>/assumir")
@staff_required
def assumir_ticket(id):
    db = get_db()
    db.execute("UPDATE ticket SET agente_id=?,estado='em_analise' WHERE id=?", (session["id"], id))
    db.commit(); db.close()
    flash("Ticket assumido.", "sucesso")
    return redirect(url_for("ver_ticket", id=id))

@app.route("/ticket/<int:id>/fechar")
@staff_required
def fechar_ticket(id):
    db = get_db()
    db.execute(
        "UPDATE ticket SET estado='fechado', fechado_em=datetime('now') WHERE id=?", (id,)
    )
    db.commit(); db.close()
    flash("Ticket fechado.", "sucesso")
    return redirect(url_for("tickets_helpdesk"))

@app.route("/ticket/<int:id>/imprimir")
@staff_required
def imprimir_ticket(id):
    db = get_db()
    ticket = db.execute(
        "SELECT t.*,u.nome AS cliente_nome,u.email AS cliente_email,u.empresa "
        "FROM ticket t JOIN utilizador u ON t.cliente_id=u.id WHERE t.id=?", (id,)
    ).fetchone()
    if not ticket or ticket["estado"] != "fechado":
        db.close(); flash("Só é possível exportar tickets fechados.", "erro")
        return redirect(url_for("ver_ticket", id=id))
    respostas = db.execute(
        "SELECT r.*,u.nome,u.tipo AS utilizador_tipo FROM resposta_ticket r "
        "JOIN utilizador u ON r.utilizador_id=u.id WHERE r.ticket_id=? ORDER BY r.id", (id,)
    ).fetchall()
    avaliacao = db.execute("SELECT * FROM avaliacao WHERE ticket_id=?", (id,)).fetchone()
    db.close()

    # Gera o HTML do ticket (template só com CSS simples, compatível com o motor de PDF)
    html = render_template("ticket_print.html",
        ticket=ticket, respostas=respostas, avaliacao=avaliacao,
        now=datetime.now().strftime("%d/%m/%Y %H:%M")
    )

    # Converte o HTML em PDF real no servidor (sem depender do print() do browser)
    pdf_buffer = BytesIO()
    resultado = pisa.CreatePDF(src=html, dest=pdf_buffer, encoding="utf-8")
    if resultado.err:
        flash("Erro ao gerar o PDF do ticket.", "erro")
        return redirect(url_for("ver_ticket", id=id))

    pdf_buffer.seek(0)
    return Response(
        pdf_buffer.read(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=ticket_{id}.pdf"
        }
    )

# ─── API polling ──────────────────────────────────────────────────────────────
@app.route("/api/ticket/<int:id>/respostas")
@login_required
def api_respostas(id):
    db = get_db()
    ticket = db.execute("SELECT * FROM ticket WHERE id=?", (id,)).fetchone()
    if not ticket:
        db.close(); return jsonify([])
    if session.get("tipo") == "cliente" and ticket["cliente_id"] != session["id"]:
        db.close(); return jsonify([])
    rows = db.execute(
        "SELECT r.id,r.mensagem,r.criado_em,u.nome,u.tipo AS utilizador_tipo,u.foto_perfil "
        "FROM resposta_ticket r JOIN utilizador u ON r.utilizador_id=u.id "
        "WHERE r.ticket_id=? ORDER BY r.id", (id,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
   app.run(host="192.168.1.141", port=5000, debug=False)
