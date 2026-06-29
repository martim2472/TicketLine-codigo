import sqlite3
import os

"""
Base de dados SQLite do Ticketline.
Cada tabela guarda um tipo de informação:
  utilizador, ticket, resposta_ticket, mensagem_contacto, etc.
"""

DB_PATH = os.path.join(os.path.dirname(__file__), 'ticketline.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _colunas(conn, tabela):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}


def init_db():
    conn = get_db()

    conn.execute('''
        CREATE TABLE IF NOT EXISTS utilizador (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT    NOT NULL,
            email         TEXT    NOT NULL UNIQUE,
            password      TEXT    NOT NULL,
            tipo          TEXT    NOT NULL DEFAULT 'cliente',
            empresa       TEXT    NOT NULL DEFAULT '',
            foto_perfil   TEXT    DEFAULT NULL,
            data_registo  DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultimo_acesso DATETIME DEFAULT NULL
        )
    ''')

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS ticket (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo     TEXT NOT NULL,
            descricao  TEXT NOT NULL,
            categoria  TEXT NOT NULL DEFAULT 'geral',
            prioridade TEXT NOT NULL DEFAULT 'normal',
            estado     TEXT NOT NULL DEFAULT 'aberto',
            cliente_id INTEGER NOT NULL REFERENCES utilizador(id),
            agente_id  INTEGER REFERENCES utilizador(id),
            criado_em  DATETIME DEFAULT CURRENT_TIMESTAMP,
            fechado_em DATETIME DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS resposta_ticket (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id     INTEGER NOT NULL REFERENCES ticket(id),
            utilizador_id INTEGER NOT NULL REFERENCES utilizador(id),
            mensagem      TEXT    NOT NULL,
            criado_em     DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS password_reset_token (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            utilizador_id INTEGER NOT NULL REFERENCES utilizador(id),
            token         TEXT    NOT NULL UNIQUE,
            expira_em     DATETIME NOT NULL,
            usado         INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS avaliacao (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id  INTEGER NOT NULL UNIQUE REFERENCES ticket(id),
            cliente_id INTEGER NOT NULL REFERENCES utilizador(id),
            agente_id  INTEGER NOT NULL REFERENCES utilizador(id),
            estrelas   INTEGER NOT NULL CHECK(estrelas BETWEEN 1 AND 5),
            comentario TEXT,
            criado_em  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS anexo_ticket (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id     INTEGER REFERENCES ticket(id),
            resposta_id   INTEGER REFERENCES resposta_ticket(id),
            utilizador_id INTEGER NOT NULL REFERENCES utilizador(id),
            filename      TEXT NOT NULL,
            criado_em     DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS mensagem_interna (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            remetente_id    INTEGER NOT NULL REFERENCES utilizador(id),
            destinatario_id INTEGER NOT NULL REFERENCES utilizador(id),
            assunto         TEXT NOT NULL DEFAULT 'Sem assunto',
            corpo           TEXT NOT NULL,
            lida            INTEGER DEFAULT 0,
            criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS mensagem_contacto (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            email     TEXT NOT NULL,
            assunto   TEXT NOT NULL,
            mensagem  TEXT NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()

    cols_util = _colunas(conn, 'utilizador')
    if 'ultimo_acesso' not in cols_util:
        conn.execute("ALTER TABLE utilizador ADD COLUMN ultimo_acesso DATETIME DEFAULT NULL")
    if 'data_registo' not in cols_util:
        conn.execute("ALTER TABLE utilizador ADD COLUMN data_registo DATETIME DEFAULT CURRENT_TIMESTAMP")
    if 'foto_perfil' not in cols_util:
        conn.execute("ALTER TABLE utilizador ADD COLUMN foto_perfil TEXT DEFAULT NULL")
    if 'empresa' not in cols_util:
        conn.execute("ALTER TABLE utilizador ADD COLUMN empresa TEXT NOT NULL DEFAULT ''")

    cols_ticket = _colunas(conn, 'ticket')
    if cols_ticket and 'criado_em' not in cols_ticket:
        conn.execute("ALTER TABLE ticket ADD COLUMN criado_em DATETIME DEFAULT CURRENT_TIMESTAMP")
        conn.execute("UPDATE ticket SET criado_em=CURRENT_TIMESTAMP WHERE criado_em IS NULL")
    if cols_ticket and 'fechado_em' not in cols_ticket:
        conn.execute("ALTER TABLE ticket ADD COLUMN fechado_em DATETIME DEFAULT NULL")
        conn.execute(
            "UPDATE ticket SET fechado_em=datetime('now') WHERE estado='fechado' AND fechado_em IS NULL"
        )

    conn.commit()
    conn.close()


def criar_admin_se_nao_existir():
    from werkzeug.security import generate_password_hash
    conn = get_db()
    if not conn.execute("SELECT id FROM utilizador WHERE tipo='admin'").fetchone():
        conn.execute(
            "INSERT INTO utilizador (nome,email,password,tipo,empresa) VALUES (?,?,?,?,?)",
            ("Administrador","admin@ticketline.pt",generate_password_hash("admin123"),"admin","Ticketline")
        )
        conn.commit()
        print("[DB] Admin criado: admin@ticketline.pt / admin123")
    conn.close()
