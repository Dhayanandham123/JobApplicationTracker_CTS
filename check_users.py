import sqlite3

conn = sqlite3.connect('database/tracker.db')
cursor = conn.cursor()
cursor.execute("SELECT id, username FROM users")
print("Users:", cursor.fetchall())
conn.close()
