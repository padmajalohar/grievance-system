import argparse
import os
import sqlite3

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "grievance.db")


def create_admin(email: str, password: str, name: str = "System Administrator"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),))
    if cursor.fetchone():
        raise SystemExit("Admin account already exists for this email.")
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role, session_token, created_at) VALUES (?, ?, ?, 'admin', NULL, datetime('now'))",
        (name, email.lower(), generate_password_hash(password)),
    )
    conn.commit()
    conn.close()
    print(f"Admin created: {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an administrator account")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Strong admin password")
    parser.add_argument("--name", default="System Administrator", help="Display name for the admin")
    args = parser.parse_args()
    create_admin(args.email, args.password, args.name)
