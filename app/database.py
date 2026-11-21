import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .config import settings


def now():
    return datetime.now(timezone.utc).isoformat()

class TicketStore:
    def __init__(self, path=None):
        self.path = str(path or settings.database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self):
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                channel TEXT NOT NULL, redacted_ticket TEXT NOT NULL,
                issue_category TEXT, assigned_team TEXT NOT NULL,
                priority TEXT, user_sentiment TEXT, confidence_score REAL,
                reasoning TEXT, pii_detected INTEGER NOT NULL,
                suspicious INTEGER NOT NULL, requires_human_review INTEGER NOT NULL,
                status TEXT NOT NULL, model_provider TEXT NOT NULL, error TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS ticket_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL,
                created_at TEXT NOT NULL, event_type TEXT NOT NULL, data TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id))''')

    @staticmethod
    def _row(row):
        if row is None:
            return None
        obj = dict(row)
        for k in ['pii_detected', 'suspicious', 'requires_human_review']:
            obj[k] = bool(obj[k])
        return obj

    def create(self, result, channel, provider):
        ticket_id = 'TKT-' + uuid4().hex[:10].upper()
        c = result.get('classification') or {}
        review = bool(result.get('requires_human_review', True))
        status = 'pending_review' if review else 'assigned'
        ts = now()
        row = (ticket_id, ts, ts, channel, result['redacted_ticket'],
               c.get('issue_category'), result.get('assigned_team', 'customer_support'),
               c.get('priority'), c.get('user_sentiment'), c.get('confidence_score'),
               c.get('reasoning'), int(result.get('pii_detected', False)),
               int(result.get('suspicious', False)), int(review), status, provider,
               result.get('error'))
        with self.connect() as db:
            db.execute('''INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', row)
            self._event(db, ticket_id, 'created', {'status': status, 'assigned_team': result.get('assigned_team')})
        return self.get(ticket_id)

    def _event(self, db, ticket_id, event_type, data):
        db.execute('INSERT INTO ticket_events(ticket_id,created_at,event_type,data) VALUES (?,?,?,?)',
                   (ticket_id, now(), event_type, json.dumps(data)))

    def get(self, ticket_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        return self._row(row)

    def list(self, status=None, limit=100):
        with self.connect() as db:
            if status:
                rows = db.execute('SELECT * FROM tickets WHERE status=? ORDER BY created_at DESC LIMIT ?', (status, limit)).fetchall()
            else:
                rows = db.execute('SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return [self._row(row) for row in rows]

    def events(self, ticket_id):
        with self.connect() as db:
            rows = db.execute('SELECT created_at,event_type,data FROM ticket_events WHERE ticket_id=? ORDER BY event_id', (ticket_id,)).fetchall()
        return [{'created_at': r['created_at'], 'event_type': r['event_type'], 'data': json.loads(r['data'])} for r in rows]

    def review(self, ticket_id, category, priority, team, note):
        with self.connect() as db:
            row = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            if row is None:
                raise KeyError('ticket not found')
            if row['status'] != 'pending_review':
                raise ValueError('only pending_review tickets may be reviewed')
            db.execute('''UPDATE tickets SET issue_category=?,priority=?,assigned_team=?,
                       requires_human_review=0,status='assigned',updated_at=? WHERE id=?''',
                       (category, priority, team, now(), ticket_id))
            self._event(db, ticket_id, 'reviewed', {'category': category, 'priority': priority, 'assigned_team': team, 'note': note})
        return self.get(ticket_id)

    def change_status(self, ticket_id, status, note):
        transitions = {'assigned': {'in_progress'}, 'in_progress': {'resolved'}}
        with self.connect() as db:
            row = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            if row is None:
                raise KeyError('ticket not found')
            if status not in transitions.get(row['status'], set()):
                raise ValueError('invalid ticket status transition')
            db.execute('UPDATE tickets SET status=?,updated_at=? WHERE id=?', (status, now(), ticket_id))
            self._event(db, ticket_id, 'status_changed', {'status': status, 'note': note})
        return self.get(ticket_id)
