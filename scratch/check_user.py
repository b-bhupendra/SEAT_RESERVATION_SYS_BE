import sqlite3

def check_user():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    cursor.execute("SELECT email, role, hashed_password FROM users WHERE email='manual@example.com';")
    row = cursor.fetchone()
    if row:
        print(f"Email: {row[0]}, Role: {row[1]}, Hashed Password: '{row[2]}'")
    else:
        print("User not found.")
    conn.close()

if __name__ == "__main__":
    check_user()
