import os
import json

DATABASE_URL = os.environ.get("DATABASE_URL")


def _connect():
    if not DATABASE_URL:
        return None
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = _connect()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS app_data (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
    finally:
        conn.close()


def load(key):
    conn = _connect()
    if not conn:
        return None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app_data WHERE key = %s", (key,))
                row = cur.fetchone()
                return json.loads(row[0]) if row else None
    finally:
        conn.close()


def save(key, data):
    conn = _connect()
    if not conn:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO app_data (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = %s",
                    (key, json.dumps(data), json.dumps(data)),
                )
        return True
    finally:
        conn.close()


def exists(key):
    conn = _connect()
    if not conn:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM app_data WHERE key = %s", (key,))
                return cur.fetchone() is not None
    finally:
        conn.close()


def migrate_from_files(data_dir):
    """Import existing JSON files into PostgreSQL on first run."""
    file_key_map = {
        "payroll_history.json": "payroll_history",
        "schedules.json": "schedules",
        "timeclock.json": "timeclock",
        "time_off.json": "time_off",
        "requests.json": "requests",
        "request_types.json": "request_types",
        "shift_swaps.json": "shift_swaps",
        "manager_notes.json": "manager_notes",
        "bills.json": "bills",
        "maintenance_log.json": "maintenance_log",
        "schedule_templates.json": "schedule_templates",
        "notifications.json": "notifications",
        "messages.json": "messages",
        "employee_tracker.json": "employee_tracker",
        "app_settings.json": "app_settings",
        "tax_settings.json": "tax_settings",
        "users.json": "users",
        "employees.json": "employees",
    }
    migrated = 0
    for filename, key in file_key_map.items():
        if not exists(key):
            filepath = os.path.join(data_dir, filename)
            if os.path.exists(filepath):
                with open(filepath) as f:
                    data = json.load(f)
                save(key, data)
                migrated += 1
    return migrated
