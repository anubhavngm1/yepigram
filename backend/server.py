import asyncio
import json
import logging
import os
import time
from aiohttp import web, WSMsgType
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ACTIVE_SESSIONS = {} # user_id -> WebSocketResponse
START_TIME = time.time()

# -------------------------------------------------------------
# Auth Helper
# -------------------------------------------------------------
def get_auth_user(request):
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif "token" in request.query:
        token = request.query["token"]
    if not token:
        return None
    return database.verify_session(token)

# -------------------------------------------------------------
# REST API Handlers
# -------------------------------------------------------------
async def health_check(request):
    return web.json_response({
        "status": "healthy",
        "service": "Yapergram E2EE Production Broker",
        "uptime_seconds": int(time.time() - START_TIME),
        "active_users": len(ACTIVE_SESSIONS)
    })

async def handle_register(request):
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    display_name = data.get("display_name", "").strip()
    avatar = data.get("avatar", "")
    identity_key = data.get("identity_key", "")

    if not username or not password:
        return web.json_response({"error": "Username and password are required"}, status=400)
    if len(username) < 3:
        return web.json_response({"error": "Username must be at least 3 characters"}, status=400)
    if len(password) < 4:
        return web.json_response({"error": "Password must be at least 4 characters"}, status=400)

    user, err = database.register_user(username, password, display_name, avatar, identity_key)
    if err:
        return web.json_response({"error": err}, status=409)
    return web.json_response({"status": "success", "user": user})

async def handle_login(request):
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return web.json_response({"error": "Username and password are required"}, status=400)

    user, err = database.login_user(username, password)
    if err:
        return web.json_response({"error": err}, status=401)
    return web.json_response({"status": "success", "user": user})

async def handle_get_me(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    return web.json_response({"status": "success", "user": user})

async def handle_logout(request):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        database.logout_user(token)
    return web.json_response({"status": "success"})

async def handle_search_users(request):
    user = get_auth_user(request)
    query = request.query.get("q", "").strip()
    my_id = user["user_id"] if user else ""
    results = database.search_users(query, my_id)
    return web.json_response({"status": "success", "users": results})

async def handle_update_profile(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    data = await request.json()
    updated = database.update_profile(
        user["user_id"],
        data.get("display_name", ""),
        data.get("avatar", ""),
        data.get("bio", "")
    )
    return web.json_response({"status": "success", "user": updated})

async def handle_get_chats(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    chats = database.get_user_chats(user["user_id"])
    return web.json_response({"status": "success", "chats": chats})

async def handle_create_chat(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    data = await request.json()
    peer_id = data.get("peer_id")
    if not peer_id:
        return web.json_response({"error": "Peer ID required"}, status=400)
    chat = database.get_or_create_chat(user["user_id"], peer_id)
    return web.json_response({"status": "success", "chat": chat})

async def handle_lock_chat(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    data = await request.json()
    chat_id = data.get("chat_id")
    pin = data.get("pin", "")
    if not chat_id or not pin:
        return web.json_response({"error": "Chat ID and PIN required"}, status=400)
    database.lock_chat(chat_id, pin)
    return web.json_response({"status": "success"})

async def handle_unlock_chat(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    data = await request.json()
    chat_id = data.get("chat_id")
    pin = data.get("pin", "")
    if not chat_id or not pin:
        return web.json_response({"error": "Chat ID and PIN required"}, status=400)
    is_valid = database.unlock_chat_verify(chat_id, pin)
    if not is_valid:
        return web.json_response({"error": "Incorrect PIN"}, status=403)
    return web.json_response({"status": "success"})

async def handle_get_messages(request):
    user = get_auth_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    peer_id = request.match_info.get("peer_id")
    msgs = database.get_chat_history(user["user_id"], peer_id)
    return web.json_response({"status": "success", "messages": msgs})

async def handle_stories(request):
    if request.method == "GET":
        stories = database.get_active_stories()
        return web.json_response({"status": "success", "stories": stories})
    elif request.method == "POST":
        user = get_auth_user(request)
        if not user:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        story = database.create_story(
            user["user_id"],
            data.get("media_url", ""),
            data.get("text_content", ""),
            data.get("bg_gradient", "")
        )
        return web.json_response({"status": "success", "story": story})

async def get_user_prekeys(request):
    user_id = request.match_info.get("user_id")
    bundle = database.get_prekey_bundle(user_id)
    if not bundle:
        return web.json_response({"error": "Pre-key bundle not found"}, status=404)
    return web.json_response(bundle)

async def register_prekeys(request):
    data = await request.json()
    user_id = data.get("user_id")
    identity_key = data.get("identity_key")
    signed_prekey = data.get("signed_prekey")
    signed_prekey_sig = data.get("signed_prekey_sig", "")
    one_time_prekeys = data.get("one_time_prekeys", [])

    if not user_id or not identity_key or not signed_prekey:
        return web.json_response({"error": "Missing required cryptographic keys"}, status=400)

    database.save_prekeys(user_id, identity_key, signed_prekey, signed_prekey_sig, one_time_prekeys)
    return web.json_response({"status": "success", "user_id": user_id})

# -------------------------------------------------------------
# Real-Time WebSocket Broker
# -------------------------------------------------------------
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    current_user_id = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue

                action = data.get("action")

                # 1. Authenticate & Join Session
                if action == "auth":
                    token = data.get("token")
                    user = database.verify_session(token) if token else None
                    if user:
                        current_user_id = user["user_id"]
                    else:
                        current_user_id = data.get("user_id")

                    if not current_user_id:
                        await ws.send_json({"type": "error", "message": "Authentication failed"})
                        continue

                    ACTIVE_SESSIONS[current_user_id] = ws
                    logging.info(f"User connected: {current_user_id}")

                    await ws.send_json({
                        "type": "auth_ack",
                        "status": "connected",
                        "user_id": current_user_id
                    })

                    # Flush offline messages
                    offline_msgs = database.get_offline_messages(current_user_id)
                    for m in offline_msgs:
                        await ws.send_json({
                            "type": "message",
                            "message_id": m["message_id"],
                            "sender_id": m["sender_id"],
                            "encrypted_payload": m["encrypted_payload"],
                            "status": m["status"],
                            "timestamp": m["timestamp"],
                            "is_offline_replay": True
                        })

                # 2. Real-Time Encrypted Message Dispatch
                elif action == "send_message":
                    sender_id = current_user_id or data.get("sender_id")
                    recipient_id = data.get("recipient_id")
                    message_id = data.get("message_id")
                    encrypted_payload = data.get("encrypted_payload")

                    if not recipient_id or not encrypted_payload or not message_id:
                        continue

                    # Serialize payload if dict
                    payload_str = json.dumps(encrypted_payload) if isinstance(encrypted_payload, dict) else str(encrypted_payload)

                    recipient_ws = ACTIVE_SESSIONS.get(recipient_id)
                    is_online = recipient_ws and not recipient_ws.closed

                    status = "delivered" if is_online else "sent"
                    database.save_message(message_id, sender_id, recipient_id, payload_str, status)

                    if is_online:
                        await recipient_ws.send_json({
                            "type": "message",
                            "message_id": message_id,
                            "sender_id": sender_id,
                            "encrypted_payload": encrypted_payload,
                            "status": "delivered",
                            "timestamp": int(time.time())
                        })

                    # Return status receipt to sender
                    await ws.send_json({
                        "type": "receipt",
                        "message_id": message_id,
                        "status": status,
                        "recipient_id": recipient_id
                    })

                # 3. Read Receipts (Double Blue Ticks)
                elif action == "read_receipt":
                    message_id = data.get("message_id")
                    sender_id = data.get("sender_id")
                    if message_id:
                        database.update_message_status(message_id, "read")
                    
                    sender_ws = ACTIVE_SESSIONS.get(sender_id)
                    if sender_ws and not sender_ws.closed:
                        await sender_ws.send_json({
                            "type": "receipt",
                            "message_id": message_id,
                            "status": "read",
                            "reader_id": current_user_id
                        })

                # 4. Typing Indicator (Real-time animated bouncing dots)
                elif action == "typing":
                    recipient_id = data.get("recipient_id")
                    is_typing = data.get("is_typing", True)
                    rec_ws = ACTIVE_SESSIONS.get(recipient_id)
                    if rec_ws and not rec_ws.closed:
                        await rec_ws.send_json({
                            "type": "typing",
                            "sender_id": current_user_id,
                            "is_typing": is_typing
                        })

    finally:
        if current_user_id and current_user_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[current_user_id]
            logging.info(f"User disconnected: {current_user_id}")

    return ws

def create_app():
    database.init_db()
    app = web.Application()

    async def cors_middleware(app, handler):
        async def middleware(request):
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                try:
                    response = await handler(request)
                except web.HTTPException as ex:
                    response = ex
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response
        return middleware

    app.middlewares.append(cors_middleware)
    app.router.add_get("/", health_check)
    app.router.add_get("/healthz", health_check)
    
    # Auth & Users
    app.router.add_post("/api/auth/register", handle_register)
    app.router.add_post("/api/auth/login", handle_login)
    app.router.add_post("/api/auth/logout", handle_logout)
    app.router.add_get("/api/auth/me", handle_get_me)
    app.router.add_get("/api/users/search", handle_search_users)
    app.router.add_post("/api/users/profile", handle_update_profile)

    # Chats & Messages
    app.router.add_get("/api/chats", handle_get_chats)
    app.router.add_post("/api/chats/create", handle_create_chat)
    app.router.add_post("/api/chats/lock", handle_lock_chat)
    app.router.add_post("/api/chats/unlock", handle_unlock_chat)
    app.router.add_get("/api/messages/{peer_id}", handle_get_messages)

    # Stories
    app.router.add_get("/api/stories", handle_stories)
    app.router.add_post("/api/stories", handle_stories)

    # Pre-keys (X3DH)
    app.router.add_get("/api/prekeys/{user_id}", get_user_prekeys)
    app.router.add_post("/api/prekeys", register_prekeys)

    # Real-Time WebSocket
    app.router.add_get("/ws", websocket_handler)

    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app = create_app()
    logging.info(f"Starting Yapergram Unified Server on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)
