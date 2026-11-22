import asyncio
import json
import logging
import os
import time
from aiohttp import web, WSMsgType
from database import init_db, register_user, save_prekeys, get_prekey_bundle, queue_offline_message, fetch_queued_messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ACTIVE_SESSIONS = {}
START_TIME = time.time()

# -------------------------------------------------------------
# HTTP REST API Handlers
# -------------------------------------------------------------
async def health_check(request):
    """Keep-alive endpoint for free hosting (pinged by UptimeRobot)."""
    return web.json_response({
        "status": "healthy",
        "service": "Yapergram E2EE Broker",
        "uptime_seconds": int(time.time() - START_TIME),
        "active_users": len(ACTIVE_SESSIONS)
    })

async def get_user_prekeys(request):
    """Retrieve peer's X3DH prekey bundle to establish E2EE session."""
    user_id = request.match_info.get("user_id")
    bundle = get_prekey_bundle(user_id)
    if not bundle:
        return web.json_response({"error": "User or pre-key bundle not found"}, status=404)
    return web.json_response(bundle)

async def register_prekeys(request):
    """Register or rotate Pre-Key bundle (IK, SPK, OPKs)."""
    data = await request.json()
    user_id = data.get("user_id")
    display_name = data.get("display_name", user_id)
    email = data.get("email", "")
    identity_key = data.get("identity_key")
    signed_prekey = data.get("signed_prekey")
    signed_prekey_sig = data.get("signed_prekey_sig", "")
    one_time_prekeys = data.get("one_time_prekeys", [])

    if not user_id or not identity_key or not signed_prekey:
        return web.json_response({"error": "Missing required cryptographic keys"}, status=400)

    register_user(user_id, display_name, email, identity_key)
    save_prekeys(user_id, identity_key, signed_prekey, signed_prekey_sig, one_time_prekeys)
    logging.info(f"Registered E2EE Pre-Key bundle for user: {user_id}")
    return web.json_response({"status": "success", "user_id": user_id})

# -------------------------------------------------------------
# Integrated WebSocket Handler (Runs on unified Cloud PORT)
# -------------------------------------------------------------
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    user_id = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue

                action = data.get("action")

                # 1. Authenticate / Connect
                if action == "auth":
                    user_id = data.get("user_id")
                    if not user_id:
                        continue
                    ACTIVE_SESSIONS[user_id] = ws
                    logging.info(f"User connected: {user_id}")

                    await ws.send_json({
                        "type": "auth_ack",
                        "status": "connected",
                        "user_id": user_id
                    })

                    # Flush queued offline messages
                    offline_msgs = fetch_queued_messages(user_id)
                    if offline_msgs:
                        logging.info(f"Flushing {len(offline_msgs)} queued messages to {user_id}")
                        for q in offline_msgs:
                            await ws.send_json({
                                "type": "message",
                                "message_id": q["message_id"],
                                "sender_id": q["sender_id"],
                                "encrypted_payload": q["encrypted_payload"],
                                "timestamp": q["timestamp"],
                                "is_offline_replay": True
                            })

                # 2. Encrypted Message Dispatch
                elif action == "send_message":
                    sender_id = user_id or data.get("sender_id")
                    recipient_id = data.get("recipient_id")
                    message_id = data.get("message_id")
                    encrypted_payload = data.get("encrypted_payload")

                    if not recipient_id or not encrypted_payload:
                        continue

                    recipient_ws = ACTIVE_SESSIONS.get(recipient_id)
                    if recipient_ws and not recipient_ws.closed:
                        await recipient_ws.send_json({
                            "type": "message",
                            "message_id": message_id,
                            "sender_id": sender_id,
                            "encrypted_payload": encrypted_payload,
                            "timestamp": int(time.time())
                        })
                        await ws.send_json({
                            "type": "receipt",
                            "message_id": message_id,
                            "status": "delivered",
                            "recipient_id": recipient_id
                        })
                    else:
                        queue_offline_message(message_id, recipient_id, sender_id, json.dumps(encrypted_payload))
                        logging.info(f"Queued offline message {message_id} for {recipient_id}")
                        await ws.send_json({
                            "type": "receipt",
                            "message_id": message_id,
                            "status": "sent",
                            "recipient_id": recipient_id
                        })

                # 3. Read Receipts
                elif action == "read_receipt":
                    sender_id = data.get("sender_id")
                    message_id = data.get("message_id")
                    sender_ws = ACTIVE_SESSIONS.get(sender_id)
                    if sender_ws and not sender_ws.closed:
                        await sender_ws.send_json({
                            "type": "receipt",
                            "message_id": message_id,
                            "status": "read",
                            "reader_id": user_id
                        })

                # 4. Typing Indicator
                elif action == "typing":
                    recipient_id = data.get("recipient_id")
                    rec_ws = ACTIVE_SESSIONS.get(recipient_id)
                    if rec_ws and not rec_ws.closed:
                        await rec_ws.send_json({
                            "type": "typing",
                            "sender_id": user_id,
                            "is_typing": data.get("is_typing", True)
                        })

            elif msg.type == WSMsgType.ERROR:
                logging.error(f"WebSocket connection closed with exception: {ws.exception()}")

    finally:
        if user_id and user_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[user_id]
            logging.info(f"User disconnected: {user_id}")

    return ws

def create_app():
    init_db()
    app = web.Application()

    async def cors_middleware(app, handler):
        async def middleware(request):
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response
        return middleware

    app.middlewares.append(cors_middleware)
    app.router.add_get("/", health_check)
    app.router.add_get("/healthz", health_check)
    app.router.add_get("/api/prekeys/{user_id}", get_user_prekeys)
    app.router.add_post("/api/prekeys", register_prekeys)
    app.router.add_get("/ws", websocket_handler)
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app = create_app()
    logging.info(f"Starting Yapergram Unified Server on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)
