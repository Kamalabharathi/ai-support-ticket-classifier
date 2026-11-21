
import sqlite3
from uuid import uuid4
from pathlib import Path

from .security import hash_password, verify_password


class AuthStore:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_owners (
                    ticket_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL
                )
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def create_user(self, username, password, role="customer"):
        if role not in ("customer", "support", "admin"):
            raise ValueError("Invalid role")

        username = username.strip().lower()
        user_id = str(uuid4())
        password_hash = hash_password(password)

        with self.connect() as db:
            db.execute(
                """INSERT INTO users
                   (id, username, password_hash, role)
                   VALUES (?, ?, ?, ?)""",
                (user_id, username, password_hash, role)
            )
            db.commit()

        return {
            "user_id": user_id,
            "username": username,
            "role": role
        }

    def get_user(self, user_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE id=?",
                (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def authenticate(self, username, password):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username=?",
                (username.strip().lower(),)
            ).fetchone()

        if not row:
            return None

        if not row["active"]:
            return None

        if not verify_password(password, row["password_hash"]):
            return None

        return dict(row)

    def link_owner(self, ticket_id, user_id):
        with self.connect() as db:
            db.execute(
                """INSERT INTO ticket_owners
                   (ticket_id, user_id) VALUES (?, ?)""",
                (ticket_id, user_id)
            )
            db.commit()

    def is_owner(self, ticket_id, user_id):
        with self.connect() as db:
            row = db.execute(
                """SELECT 1 FROM ticket_owners
                   WHERE ticket_id=? AND user_id=?""",
                (ticket_id, user_id)
            ).fetchone()
        return row is not None

    def list_owned(self, user_id, status=None, limit=100):
        query = """
            SELECT t.* FROM tickets t
            JOIN ticket_owners o ON t.id=o.ticket_id
            WHERE o.user_id=?
        """
        params = [user_id]

        if status:
            query += " AND t.status=?"
            params.append(status)

        query += " ORDER BY t.created_at DESC LIMIT ?"
        params.append(limit)

        with self.connect() as db:
            rows = db.execute(query, params).fetchall()

        from .database import TicketStore
        return [TicketStore._row(row) for row in rows]
