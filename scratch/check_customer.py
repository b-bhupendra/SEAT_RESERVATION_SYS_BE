import sqlite3

def check_db():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, email, status FROM customers WHERE email='testuser@example.com';")
    row = cursor.fetchone()
    if row:
        print(f"Name: {row[0]}, Email: {row[1]}, Status: {row[2]}")
    else:
        print("Customer not found.")
    conn.close()

if __name__ == "__main__":
    check_db()
