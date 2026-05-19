import sqlite3

def list_users():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT email, role FROM users;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"Email: {row[0]}, Role: {row[1]}")
    conn.close()

if __name__ == "__main__":
    list_users()
