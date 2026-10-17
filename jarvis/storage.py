from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY, text TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, arguments TEXT NOT NULL,
                    result TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY, text TEXT NOT NULL, due REAL NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                    starts_at REAL NOT NULL, ends_at REAL NOT NULL,
                    all_day INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
                    remind_minutes INTEGER NOT NULL DEFAULT 10,
                    notified INTEGER NOT NULL DEFAULT 0, cancelled INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS calendar_dates ON calendar_events(starts_at,ends_at);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def memories(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM memory ORDER BY id DESC LIMIT 100")]

    def remember(self, text):
        with self.connect() as db:
            existing = db.execute("SELECT id FROM memory WHERE text=?", (text,)).fetchone()
            if existing:
                return existing["id"]
            return db.execute("INSERT INTO memory(text,created) VALUES (?,?)",
                              (text[:500], datetime.now(timezone.utc).isoformat())).lastrowid

    def forget(self, item_id):
        with self.connect() as db:
            return db.execute("DELETE FROM memory WHERE id=?", (item_id,)).rowcount > 0

    def log(self, name, arguments, result):
        with self.connect() as db:
            db.execute("INSERT INTO actions(name,arguments,result,created) VALUES (?,?,?,?)",
                       (name, json.dumps(arguments, ensure_ascii=False),
                        json.dumps(result, ensure_ascii=False, default=str)[:16000],
                        datetime.now(timezone.utc).isoformat()))

    def actions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM actions ORDER BY id DESC LIMIT 60")]

    def reminders(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM reminders WHERE done=0 ORDER BY due LIMIT 100")]

    def add_reminder(self, text, due):
        with self.connect() as db:
            return db.execute("INSERT INTO reminders(text,due) VALUES (?,?)", (text[:500], due)).lastrowid

    def finish_reminder(self, item_id):
        with self.connect() as db:
            return db.execute("UPDATE reminders SET done=1 WHERE id=? AND done=0", (item_id,)).rowcount > 0


    def events(self, start, end):
        from .calendar import event_json
        with self.connect() as db:
            return [event_json(dict(r)) for r in db.execute(
                "SELECT * FROM calendar_events WHERE cancelled=0 AND starts_at<? AND ends_at>? ORDER BY starts_at LIMIT 500",
                (end, start))]

    def event(self, item_id):
        from .calendar import event_json
        with self.connect() as db:
            row = db.execute("SELECT * FROM calendar_events WHERE id=? AND cancelled=0", (item_id,)).fetchone()
            return event_json(dict(row)) if row else None

    def save_event(self, event, item_id=None):
        values = event.record()
        with self.connect() as db:
            if item_id is None:
                cursor = db.execute(
                    "INSERT INTO calendar_events(title,starts_at,ends_at,all_day,notes,remind_minutes) VALUES (?,?,?,?,?,?)",
                    tuple(values.values()))
                item_id = cursor.lastrowid
            elif not db.execute(
                    "UPDATE calendar_events SET title=?,starts_at=?,ends_at=?,all_day=?,notes=?,remind_minutes=?,notified=0 WHERE id=? AND cancelled=0",
                    (*values.values(), item_id)).rowcount:
                raise ValueError("Calendar event not found")
        return self.event(item_id)

    def delete_event(self, item_id):
        with self.connect() as db:
            return db.execute("UPDATE calendar_events SET cancelled=1 WHERE id=? AND cancelled=0", (item_id,)).rowcount > 0

    def due_events(self, now):
        from .calendar import event_json
        with self.connect() as db:
            return [event_json(dict(r)) for r in db.execute(
                "SELECT * FROM calendar_events WHERE cancelled=0 AND notified=0 AND remind_minutes>=0 "
                "AND starts_at-remind_minutes*60<=? AND ends_at>? ORDER BY starts_at LIMIT 20", (now, now))]

    def notify_event(self, item_id):
        with self.connect() as db:
            db.execute("UPDATE calendar_events SET notified=1 WHERE id=?", (item_id,))


    def reminder(self, item_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM reminders WHERE id=? AND done=0",(item_id,)).fetchone()
            return dict(row) if row else None

    def update_reminder(self, item_id, text, due):
        with self.connect() as db:
            return db.execute("UPDATE reminders SET text=?,due=? WHERE id=? AND done=0",
                              (text[:500],due,item_id)).rowcount > 0
