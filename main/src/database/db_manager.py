import sqlite3


def connect_db():
    return sqlite3.connect('articles.db')


def create_tables():
    conn = connect_db()
    cursor = conn.cursor()
    with open('schema.sql') as f:
        cursor.executescript(f.read())
    conn.commit()
    conn.close()
