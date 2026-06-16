"""
Simple migration to add tracking and offer redemption fields.
Run with: python migrations/0002_add_tracking.py
"""
import sqlite3
import os
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), '..', 'instance', 'baasket.db')
DB = os.path.abspath(DB)
if not os.path.exists(DB):
    print('Database not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Helper to add column if missing

def ensure_col(table, coldef):
    name = coldef.split()[0]
    cur.execute(f"PRAGMA table_info('{table}')")
    existing = [r[1] for r in cur.fetchall()]
    if name not in existing:
        print('Adding', name, 'to', table)
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")

# Add columns
ensure_col('order_model', "tracking_status TEXT")
ensure_col('order_model', "tracking_updated_at DATETIME")
ensure_col('order_model', "offer_id INTEGER")

ensure_col('offer', "accepted_at DATETIME")
ensure_col('offer', "redeemed INTEGER")
ensure_col('offer', "redeemed_at DATETIME")

conn.commit()
print('Migration complete.')
conn.close()
