"""
Simple migration script to add new columns to the development SQLite database.
Run with: python migrations/0001_add_fields.py
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'instance', 'baasket.db')
DB = os.path.abspath(DB)
if not os.path.exists(DB):
    print('Database not found at', DB)
    raise SystemExit(1)

changes = {
    'user': [('legal_name','TEXT'),('ic_number','TEXT'),('home_address','TEXT'),('city','TEXT'),('region','TEXT'),('phone_number','TEXT'),('country','TEXT'),('last_seen','TEXT')],
    'listing_model':[('quantity','INTEGER'),('sku','TEXT'),('is_active','INTEGER')],
    'offer':[('buyer_id','INTEGER'),('status','TEXT')],
    'cart':[('items_json','TEXT')],
    'payment':[('buyer_id','INTEGER'),('order_id','INTEGER'),('gateway_reference','TEXT'),('provider','TEXT')]
}

conn = sqlite3.connect(DB)
cur = conn.cursor()
for table, cols in changes.items():
    cur.execute(f"PRAGMA table_info('{table}')")
    existing = [r[1] for r in cur.fetchall()]
    for cname, ctype in cols:
        if cname not in existing:
            print('Adding', cname, 'to', table)
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {cname} {ctype}")
conn.commit()
print('Migration complete.')
conn.close()
