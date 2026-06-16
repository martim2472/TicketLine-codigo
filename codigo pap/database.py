import sqlite3
import os

# Caminho do ficheiro da base de dados
DB_PATH = os.path.join(os.path.dirname(__file__), 'ticketline.db')

def get_db():
    """Abre uma ligação à base de dados."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite aceder às colunas pelo nome
    return conn

def init_db():
    """Cria as tabelas se ainda não existirem."""
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS utilizador (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            nome     TEXT NOT NULL,
            email    TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            tipo     TEXT NOT NULL CHECK(tipo IN ('cliente', 'helpdesk'))
        );

        CREATE TABLE IF NOT EXISTS ticket (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo      TEXT NOT NULL,
            descricao   TEXT NOT NULL,
            estado      TEXT NOT NULL DEFAULT 'aberto',
            criado_por  INTEGER NOT NULL REFERENCES utilizador(id),
            atribuido_a INTEGER REFERENCES utilizador(id)
        );
    ''')
    conn.commit()
    conn.close()
