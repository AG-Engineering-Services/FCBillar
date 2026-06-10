import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get schema for ranking_entries table
cur.execute("PRAGMA table_info(ranking_entries)")
print("=== ranking_entries table schema ===")
for row in cur.fetchall():
    print(row)

conn.close()
