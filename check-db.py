import sqlite3
c = sqlite3.connect("/opt/uc-chat/uc_chat.db")
print("rooms:")
for r in c.execute("SELECT id, kind, title, owner FROM rooms"):
    print("  ", r)
print("users:", [r[0] for r in c.execute("SELECT name FROM users")])
print("members:")
for r in c.execute("SELECT room_id, username FROM members ORDER BY room_id"):
    print("  ", r)
print("messages:", list(c.execute("SELECT count(*) FROM messages"))[0][0])
