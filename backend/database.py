import sqlite3
import os
import json
import time
import hashlib
import secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "yapergram.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: str = None) -> tuple:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return hashed, salt

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table with username & password auth
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        display_name TEXT NOT NULL,
        avatar TEXT DEFAULT '',
        bio TEXT DEFAULT 'Hey there! I am using Yapergram 🔒',
        identity_key TEXT DEFAULT '',
        created_at INTEGER NOT NULL
    )
    """)

    # Auth Sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    # Chats table (stores conversation metadata, locked chats, and PIN)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        chat_id TEXT PRIMARY KEY,
        user1_id TEXT NOT NULL,
        user2_id TEXT NOT NULL,
        is_locked INTEGER DEFAULT 0,
        pin_hash TEXT DEFAULT '',
        last_message TEXT DEFAULT '',
        last_timestamp INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL
    )
    """)

    # Messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT PRIMARY KEY,
        sender_id TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        encrypted_payload TEXT NOT NULL,
        status TEXT DEFAULT 'sent', -- pending, sent, delivered, read
        timestamp INTEGER NOT NULL
    )
    """)

    # 24h Stories table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        story_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        media_url TEXT DEFAULT '',
        text_content TEXT DEFAULT '',
        bg_gradient TEXT DEFAULT '',
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    # Pre-Key Bundles for X3DH session handshakes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prekeys (
        user_id TEXT PRIMARY KEY,
        identity_key TEXT NOT NULL,
        signed_prekey TEXT NOT NULL,
        signed_prekey_sig TEXT NOT NULL,
        one_time_prekeys_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    conn.commit()
    conn.close()

# -------------------------------------------------------------
# User Authentication & Profiles
# -------------------------------------------------------------
def register_user(username, password, display_name="", avatar="", identity_key=""):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if username exists
    cursor.execute("SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)", (username,))
    if cursor.fetchone():
        conn.close()
        return None, "Username already taken. Please choose another."

    user_id = f"usr_{secrets.token_hex(8)}"
    pwd_hash, salt = hash_password(password)
    disp = display_name if display_name.strip() else username
    created_at = int(time.time())

    cursor.execute("""
    INSERT INTO users (user_id, username, password_hash, salt, display_name, avatar, bio, identity_key, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, pwd_hash, salt, disp, avatar, "Hey there! I am using Yapergram 🔒", identity_key, created_at))

    # Create session token
    token = secrets.token_hex(32)
    cursor.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, created_at))

    conn.commit()
    conn.close()
    return {
        "user_id": user_id,
        "username": username,
        "display_name": disp,
        "avatar": avatar,
        "token": token
    }, None

def login_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None, "Invalid username or password"

    pwd_hash, _ = hash_password(password, row["salt"])
    if pwd_hash != row["password_hash"]:
        conn.close()
        return None, "Invalid username or password"

    token = secrets.token_hex(32)
    cursor.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, row["user_id"], int(time.time())))
    conn.commit()
    conn.close()

    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar": row["avatar"],
        "bio": row["bio"],
        "identity_key": row["identity_key"],
        "token": token
    }, None

def verify_session(token):
    if not token:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.user_id, u.username, u.display_name, u.avatar, u.bio, u.identity_key 
    FROM sessions s 
    JOIN users u ON s.user_id = u.user_id 
    WHERE s.token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def logout_user(token):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def search_users(query, current_user_id=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_id, username, display_name, avatar, bio, identity_key
    FROM users
    WHERE (LOWER(username) LIKE LOWER(?) OR LOWER(display_name) LIKE LOWER(?))
    AND user_id != ?
    LIMIT 20
    """, (f"%{query}%", f"%{query}%", current_user_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_profile(user_id, display_name, avatar, bio):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users 
    SET display_name = COALESCE(NULLIF(?, ''), display_name),
        avatar = COALESCE(NULLIF(?, ''), avatar),
        bio = COALESCE(NULLIF(?, ''), bio)
    WHERE user_id = ?
    """, (display_name, avatar, bio, user_id))
    conn.commit()
    cursor.execute("SELECT user_id, username, display_name, avatar, bio FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# -------------------------------------------------------------
# Pre-Key Bundles (X3DH)
# -------------------------------------------------------------
def save_prekeys(user_id, identity_key, signed_prekey, signed_prekey_sig, one_time_prekeys):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO prekeys (user_id, identity_key, signed_prekey, signed_prekey_sig, one_time_prekeys_json, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, identity_key, signed_prekey, signed_prekey_sig, json.dumps(one_time_prekeys), int(time.time())))
    # Also update user identity key
    cursor.execute("UPDATE users SET identity_key = ? WHERE user_id = ?", (identity_key, user_id))
    conn.commit()
    conn.close()

def get_prekey_bundle(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prekeys WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    one_time_keys = json.loads(row["one_time_prekeys_json"])
    consumed_key = None
    if one_time_keys:
        consumed_key = one_time_keys.pop(0)
        cursor.execute("UPDATE prekeys SET one_time_prekeys_json = ? WHERE user_id = ?", 
                       (json.dumps(one_time_keys), user_id))
        conn.commit()

    conn.close()
    return {
        "user_id": row["user_id"],
        "identity_key": row["identity_key"],
        "signed_prekey": row["signed_prekey"],
        "signed_prekey_sig": row["signed_prekey_sig"],
        "one_time_prekey": consumed_key
    }

# -------------------------------------------------------------
# Messages & Chat Lock (Hidden Chats)
# -------------------------------------------------------------
def get_or_create_chat(user1_id, user2_id):
    # Normalize order so chat between A and B is unique
    u1, u2 = sorted([user1_id, user2_id])
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chats WHERE user1_id = ? AND user2_id = ?", (u1, u2))
    row = cursor.fetchone()
    if row:
        chat = dict(row)
        conn.close()
        return chat
    
    chat_id = f"chat_{secrets.token_hex(8)}"
    cursor.execute("""
    INSERT INTO chats (chat_id, user1_id, user2_id, is_locked, pin_hash, created_at, last_timestamp)
    VALUES (?, ?, ?, 0, '', ?, ?)
    """, (chat_id, u1, u2, int(time.time()), int(time.time())))
    conn.commit()
    cursor.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
    chat = dict(cursor.fetchone())
    conn.close()
    return chat

def lock_chat(chat_id, pin):
    conn = get_connection()
    cursor = conn.cursor()
    pin_hash = hashlib.sha256(pin.encode('utf-8')).hexdigest()
    cursor.execute("UPDATE chats SET is_locked = 1, pin_hash = ? WHERE chat_id = ?", (pin_hash, chat_id))
    conn.commit()
    conn.close()
    return True

def unlock_chat_verify(chat_id, pin):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pin_hash FROM chats WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row["pin_hash"]:
        return True
    return hashlib.sha256(pin.encode('utf-8')).hexdigest() == row["pin_hash"]

def get_user_chats(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.*, 
           CASE WHEN c.user1_id = ? THEN u2.username ELSE u1.username END as peer_username,
           CASE WHEN c.user1_id = ? THEN u2.display_name ELSE u1.display_name END as peer_display_name,
           CASE WHEN c.user1_id = ? THEN u2.avatar ELSE u1.avatar END as peer_avatar,
           CASE WHEN c.user1_id = ? THEN u2.user_id ELSE u1.user_id END as peer_user_id
    FROM chats c
    JOIN users u1 ON c.user1_id = u1.user_id
    JOIN users u2 ON c.user2_id = u2.user_id
    WHERE c.user1_id = ? OR c.user2_id = ?
    ORDER BY c.last_timestamp DESC
    """, (user_id, user_id, user_id, user_id, user_id, user_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_message(message_id, sender_id, recipient_id, encrypted_payload, status='sent'):
    conn = get_connection()
    cursor = conn.cursor()
    now = int(time.time())
    cursor.execute("""
    INSERT OR REPLACE INTO messages (message_id, sender_id, recipient_id, encrypted_payload, status, timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (message_id, sender_id, recipient_id, encrypted_payload, status, now))
    
    # Update chat last_timestamp and last_message summary
    u1, u2 = sorted([sender_id, recipient_id])
    cursor.execute("""
    UPDATE chats 
    SET last_message = 'Encrypted message 🔒', last_timestamp = ? 
    WHERE user1_id = ? AND user2_id = ?
    """, (now, u1, u2))

    conn.commit()
    conn.close()

def update_message_status(message_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE messages SET status = ? WHERE message_id = ?", (status, message_id))
    conn.commit()
    conn.close()

def get_offline_messages(recipient_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM messages 
    WHERE recipient_id = ? AND status IN ('sent', 'pending')
    ORDER BY timestamp ASC
    """, (recipient_id,))
    rows = cursor.fetchall()
    msgs = [dict(r) for r in rows]
    # Mark as delivered
    cursor.execute("UPDATE messages SET status = 'delivered' WHERE recipient_id = ? AND status = 'sent'", (recipient_id,))
    conn.commit()
    conn.close()
    return msgs

def get_chat_history(user1_id, user2_id, limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM messages 
    WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
    ORDER BY timestamp ASC
    LIMIT ?
    """, (user1_id, user2_id, user2_id, user1_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -------------------------------------------------------------
# Stories (24h Disappearing Statuses)
# -------------------------------------------------------------
def create_story(user_id, media_url="", text_content="", bg_gradient=""):
    conn = get_connection()
    cursor = conn.cursor()
    story_id = f"story_{secrets.token_hex(8)}"
    now = int(time.time())
    expires = now + 86400 # 24 hours
    cursor.execute("""
    INSERT INTO stories (story_id, user_id, media_url, text_content, bg_gradient, created_at, expires_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (story_id, user_id, media_url, text_content, bg_gradient, now, expires))
    conn.commit()
    cursor.execute("""
    SELECT s.*, u.username, u.display_name, u.avatar 
    FROM stories s 
    JOIN users u ON s.user_id = u.user_id 
    WHERE s.story_id = ?
    """, (story_id,))
    story = dict(cursor.fetchone())
    conn.close()
    return story

def get_active_stories():
    conn = get_connection()
    cursor = conn.cursor()
    now = int(time.time())
    cursor.execute("""
    SELECT s.*, u.username, u.display_name, u.avatar 
    FROM stories s 
    JOIN users u ON s.user_id = u.user_id 
    WHERE s.expires_at > ?
    ORDER BY s.created_at DESC
    """, (now,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
