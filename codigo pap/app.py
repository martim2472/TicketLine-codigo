from flask import Flask, render_template, request, redirect, url_for, flash, session
from database import get_db, init_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_secreta_pap_ticketline'

# Inicia a base de dados (cria as tabelas se não existirem)
init_db()

# --- Página Inicial ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Registo de Utilizadores ---
@app.route('/registo', methods=['GET', 'POST'])
def registo():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        password = request.form['password']
        tipo = request.form['tipo']

        db = get_db()
        # Verifica se o email já existe
        if db.execute('SELECT id FROM utilizador WHERE email = ?', (email,)).fetchone():
            flash('Este email já está registado.', 'erro')
            db.close()
            return redirect(url_for('registo'))

        # Insere o novo utilizador na base de dados (password em texto limpo)
        db.execute('INSERT INTO utilizador (nome, email, password, tipo) VALUES (?, ?, ?, ?)',
                   (nome, email, password, tipo))
        db.commit()
        db.close()
        
        flash('Conta criada com sucesso! Já podes entrar.', 'sucesso')
        return redirect(url_for('login'))

    return render_template('registo.html')

# --- Iniciar Sessão (Login Único) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        # Procura o utilizador com o email e password correspondentes
        user = db.execute('SELECT * FROM utilizador WHERE email = ? AND password = ?', (email, password)).fetchone()
        db.close()

        # Se encontrou o utilizador, inicia a sessão
        if user:
            session['id'] = user['id']
            session['nome'] = user['nome']
            session['tipo'] = user['tipo']
            
            # Redireciona conforme o tipo de conta (cliente ou helpdesk)
            if user['tipo'] == 'cliente':
                return redirect(url_for('dashboard_cliente'))
            else:
                return redirect(url_for('dashboard_helpdesk'))
                
        flash('Email ou palavra-passe incorretos.', 'erro')

    return render_template('login.html')

# --- Terminar Sessão (Logout) ---
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Painel do Cliente ---
@app.route('/dashboard/cliente')
def dashboard_cliente():
    if session.get('tipo') != 'cliente':
        return redirect(url_for('login'))
    return render_template('dashboard_cliente.html')

# --- Painel do Agente (Helpdesk) ---
@app.route('/dashboard/helpdesk')
def dashboard_helpdesk():
    if session.get('tipo') != 'helpdesk':
        return redirect(url_for('login'))
    return render_template('dashboard_helpdesk.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
