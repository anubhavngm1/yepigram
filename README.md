# Yepigram: 100% Free Lifetime E2EE Social & Chat Platform

Yepigram is an end-to-end encrypted (E2EE) real-time messaging and social media platform with a **Liquid Glassmorphism (VisionOS / iOS 18)** user interface. It combines the private messaging of WhatsApp with the media feed and 24h stories of Instagram.

Built for **non-profit operations with a guaranteed $0/month lifetime budget and zero credit card attachment**.

---

## 📁 Project Architecture

```
yepigram/
├── backend/
│   ├── server.py             # Async WebSocket & HTTP REST edge broker (Port 8000 & 8765)
│   ├── database.py           # SQLite zero-knowledge queue & pre-key store
│   ├── requirements.txt      # websockets, aiohttp, cryptography
│   └── Dockerfile            # 1-click free container deployment for Koyeb / Render
├── client/
│   ├── index.html            # Production PWA with 3D liquid glass UI & WebCrypto E2EE
│   ├── manifest.json         # Standalone iPad & Android home screen installation manifest
│   └── sw.js                 # Service worker for offline caching & VAPID Web Push
├── test_e2ee.py              # Automated 10-step cryptographic & queue verification suite
└── README.md                 # Setup and deployment documentation
```

---

## 🚀 Running Locally (Zero Setup)

### 1. Run the Cryptographic Verification Suite
```bash
python test_e2ee.py
```
*Verifies Curve25519 X3DH key agreement, Double Ratchet AES-256-GCM encryption, offline queueing, and zero-knowledge database purging.*

### 2. Start the Backend WebSocket Broker
```bash
cd backend
python server.py
```
- **WebSocket Broker**: `ws://localhost:8765`
- **HTTP REST & Health-Check**: `http://localhost:8000/healthz`

### 3. Open the Client (Web, iPad, Android)
Simply open `client/index.html` in your browser, or serve it locally:
```bash
cd client
python -m http.server 3000
```
Open **`http://localhost:3000`** on your browser, iPad Safari, or Android Chrome!

---

## ☁️ Free Lifetime Cloud Deployment (Zero Credit Card)

When you are ready to publish Yepigram to the cloud for $0:

| Service | Purpose | Setup Instructions (No Credit Card) |
| :--- | :--- | :--- |
| **Koyeb / Render** | Backend WebSockets | 1. Sign up with GitHub (no card).<br>2. Select "New Web Service" from your GitHub repo.<br>3. Koyeb/Render auto-detects `Dockerfile`.<br>4. You receive a free permanent URL (e.g., `yepigram.koyeb.app`). |
| **Turso** | Database | 1. Sign up at [turso.tech](https://turso.tech) with GitHub (9 GB free, no card).<br>2. Create database `yepigram-db`.<br>3. Copy database URL and token into backend config. |
| **Cloudflare Pages** | Frontend Web/PWA | 1. Connect GitHub repo to Cloudflare Pages.<br>2. Point directory to `/client`.<br>3. Deployed automatically to `yepigram.pages.dev` with free SSL. |
| **UptimeRobot** | 24/7 Keep-Alive | 1. Sign up at [uptimerobot.com](https://uptimerobot.com) (free, no card).<br>2. Add an HTTP monitor to `https://yepigram.koyeb.app/healthz` pinging every 10 min. |
| **Firebase FCM** | Android Push | 1. Sign up at [firebase.google.com](https://firebase.google.com) on Spark plan (no card).<br>2. Download `google-services.json` for background push. |
