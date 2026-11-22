import sqlite3
import os
import json
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "yepigram.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        email TEXT UNIQUE,
        identity_key TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )
    """)

    # Pre-Key Bundles table for X3DH session handshakes
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

    # Ephemeral message queue for offline recipients (zero-knowledge envelopes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS message_queue (
        message_id TEXT PRIMARY KEY,
        recipient_id TEXT NOT NULL,
        sender_id TEXT NOT NULL,
        encrypted_payload TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        status TEXT DEFAULT 'queued'
    )
    """)

    conn.commit()
    conn.close()

def register_user(user_id, display_name, email, identity_key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO users (user_id, display_name, email, identity_key, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, display_name, email, identity_key, int(time.time())))
    conn.commit()
    conn.close()

def save_prekeys(user_id, identity_key, signed_prekey, signed_prekey_sig, one_time_prekeys):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO prekeys (user_id, identity_key, signed_prekey, signed_prekey_sig, one_time_prekeys_json, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, identity_key, signed_prekey, signed_prekey_sig, json.dumps(one_time_prekeys), int(time.time())))
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
        # Update remaining one-time keys
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

def queue_offline_message(message_id, recipient_id, sender_id, encrypted_payload):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO message_queue (message_id, recipient_id, sender_id, encrypted_payload, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (message_id, recipient_id, sender_id, encrypted_payload, int(time.time())))
    conn.commit()
    conn.close()

def fetch_queued_messages(recipient_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM message_queue WHERE recipient_id = ? ORDER BY timestamp ASC", (recipient_id,))
    rows = cursor.fetchall()
    messages = [dict(row) for row in rows]
    # Delete delivered messages immediately to preserve zero-knowledge ephemeral privacy
    cursor.execute("DELETE FROM message_queue WHERE recipient_id = ?", (recipient_id,))
    conn.commit()
    conn.close()
    return messages
