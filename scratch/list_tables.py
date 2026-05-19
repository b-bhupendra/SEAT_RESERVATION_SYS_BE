import sqlite3

def list_tables():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    rows = cursor.fetchall()
    for row in rows:
        print(row[0])
    conn.close()

if __name__ == "__main__":
    list_tables()
