"""
Migration to migrate offer.buyer_name into buyer_id where possible, archive legacy names, and remove the buyer_name column.
Run with: python migrations/0002_remove_offer_buyer_name.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), '..', 'instance', 'baasket.db')
DB = os.path.abspath(DB)
if not os.path.exists(DB):
    print('Database not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Create archive table for legacy names
cur.execute('''CREATE TABLE IF NOT EXISTS offer_legacy_name (
    offer_id INTEGER PRIMARY KEY,
    legacy_name TEXT
)''')

# Map existing offers to users where possible
cur.execute('SELECT id, buyer_name FROM offer')
rows = cur.fetchall()
for offer_id, buyer_name in rows:
    if buyer_name is None:
        continue
    cur.execute('SELECT id FROM user WHERE username = ?', (buyer_name,))
    r = cur.fetchone()
    if r:
        user_id = r[0]
        cur.execute('UPDATE offer SET buyer_id = ? WHERE id = ?', (user_id, offer_id))
    else:
        cur.execute('INSERT OR REPLACE INTO offer_legacy_name (offer_id, legacy_name) VALUES (?,?)', (offer_id, buyer_name))
conn.commit()

# Recreate offer table without buyer_name column
# Get existing schema
cur.execute("PRAGMA table_info('offer')")
cols = [r[1] for r in cur.fetchall()]
print('Existing offer columns:', cols)
# Create new table
cur.execute('''CREATE TABLE IF NOT EXISTS offer_new (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL,
    buyer_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    amount NUMERIC NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at DATETIME
)''')
# Copy data
cur.execute('SELECT id, listing_id, buyer_id, status, amount, message, created_at FROM offer')
raw = cur.fetchall()
allrows = []
for row in raw:
    (oid, lid, bid, status, amount, message, created_at) = row
    if status is None:
        status = 'pending'
    allrows.append((oid, lid, bid, status, amount, message, created_at))
cur.executemany('INSERT INTO offer_new (id, listing_id, buyer_id, status, amount, message, created_at) VALUES (?,?,?,?,?,?,?)', allrows)
conn.commit()
# Drop old offer table and rename new
cur.execute('DROP TABLE offer')
cur.execute('ALTER TABLE offer_new RENAME TO offer')
conn.commit()
print('Migration complete.')
conn.close()
