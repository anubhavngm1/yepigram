import asyncio
import json
import logging
import os
import time
from aiohttp import web
import websockets
from database import init_db, register_user, save_prekeys, get_prekey_bundle, queue_offline_message, fetch_queued_messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# In-memory registry of active WebSocket sessions: user_id -> websocket
ACTIVE_SESSIONS = {}
START_TIME = time.time()

# -------------------------------------------------------------
# HTTP REST API Handlers (Health check & Pre-key registration)
# -------------------------------------------------------------
async def health_check(request):
    """Keep-alive endpoint for free hosting (pinged by UptimeRobot)."""
    return web.json_response({
        "status": "healthy",
        "service": "Yepigram E2EE Broker",
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
# Real-Time WebSocket Broker Handlers
# -------------------------------------------------------------
async def ws_handler(websocket):
    user_id = None
    try:
        async for raw_message in websocket:
            try:
                msg = json.loads(raw_message)
            except Exception:
                continue

            action = msg.get("action")

            # 1. User Authenticate / Connect
            if action == "auth":
                user_id = msg.get("user_id")
                if not user_id:
                    continue
                ACTIVE_SESSIONS[user_id] = websocket
                logging.info(f"User connected & authenticated: {user_id}")
                
                # Acknowledge connection
                await websocket.send(json.dumps({
                    "type": "auth_ack",
                    "status": "connected",
                    "user_id": user_id
                }))

                # Flush any queued offline messages
                offline_msgs = fetch_queued_messages(user_id)
                if offline_msgs:
                    logging.info(f"Flushing {len(offline_msgs)} queued messages to {user_id}")
                    for queued in offline_msgs:
                        await websocket.send(json.dumps({
                            "type": "message",
                            "message_id": queued["message_id"],
                            "sender_id": queued["sender_id"],
                            "encrypted_payload": queued["encrypted_payload"],
                            "timestamp": queued["timestamp"],
                            "is_offline_replay": True
                        }))

            # 2. Encrypted Message Dispatch (Zero-Knowledge Routing)
            elif action == "send_message":
                sender_id = user_id or msg.get("sender_id")
                recipient_id = msg.get("recipient_id")
                message_id = msg.get("message_id")
                encrypted_payload = msg.get("encrypted_payload")

                if not recipient_id or not encrypted_payload:
                    continue

                # Is recipient online?
                recipient_ws = ACTIVE_SESSIONS.get(recipient_id)
                if recipient_ws and recipient_ws.open:
                    # Direct instant delivery
                    await recipient_ws.send(json.dumps({
                        "type": "message",
                        "message_id": message_id,
                        "sender_id": sender_id,
                        "encrypted_payload": encrypted_payload,
                        "timestamp": int(time.time())
                    }))
                    # Send delivery receipt back to sender
                    await websocket.send(json.dumps({
                        "type": "receipt",
                        "message_id": message_id,
                        "status": "delivered",
                        "recipient_id": recipient_id
                    }))
                else:
                    # Recipient is offline -> Queue in SQLite zero-knowledge storage
                    queue_offline_message(message_id, recipient_id, sender_id, encrypted_payload)
                    logging.info(f"Queued offline message {message_id} for {recipient_id}")
                    # Send 'sent' confirmation back to sender
                    await websocket.send(json.dumps({
                        "type": "receipt",
                        "message_id": message_id,
                        "status": "sent",
                        "recipient_id": recipient_id
                    }))

            # 3. Read Receipts (Double Blue Ticks)
            elif action == "read_receipt":
                sender_id = msg.get("sender_id")
                message_id = msg.get("message_id")
                sender_ws = ACTIVE_SESSIONS.get(sender_id)
                if sender_ws and sender_ws.open:
                    await sender_ws.send(json.dumps({
                        "type": "receipt",
                        "message_id": message_id,
                        "status": "read",
                        "reader_id": user_id
                    }))

            # 4. Typing Indicator
            elif action == "typing":
                recipient_id = msg.get("recipient_id")
                is_typing = msg.get("is_typing", True)
                rec_ws = ACTIVE_SESSIONS.get(recipient_id)
                if rec_ws and rec_ws.open:
                    await rec_ws.send(json.dumps({
                        "type": "typing",
                        "sender_id": user_id,
                        "is_typing": is_typing
                    }))

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if user_id and user_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[user_id]
            logging.info(f"User disconnected: {user_id}")

# -------------------------------------------------------------
# Main Combined Server Runner
# -------------------------------------------------------------
async def main():
    init_db()

    # HTTP Server on Port 8000
    app = web.Application()
    # CORS middleware
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

    http_runner = web.AppRunner(app)
    await http_runner.setup()
    http_site = web.TCPSite(http_runner, "0.0.0.0", 8000)
    await http_site.start()
    logging.info("Yepigram HTTP REST & Keep-Alive server running on http://0.0.0.0:8000")

    # WebSocket Server on Port 8765
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        logging.info("Yepigram E2EE WebSocket Broker running on ws://0.0.0.0:8765")
        await asyncio.Future() # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server terminated.")
