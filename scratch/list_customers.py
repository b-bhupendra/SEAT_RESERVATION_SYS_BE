import sqlite3

def list_customers():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, email, status FROM customers;")
    rows = cursor.fetchall()
    for row in rows:
        print(f"Name: {row[0]}, Email: {row[1]}, Status: {row[2]}")
    conn.close()

if __name__ == "__main__":
    list_customers()
