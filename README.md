# Yapergram: 100% Free Lifetime E2EE Social & Chat Platform

Yapergram is an end-to-end encrypted (E2EE) real-time messaging and social media platform with a **Liquid Glassmorphism (VisionOS / iOS 18)** user interface. It combines the private messaging of WhatsApp with the media feed and 24h stories of Instagram.

Built for **non-profit operations with a guaranteed $0/month lifetime budget and zero credit card attachment**.

---

## 🌐 Live Cloud Deployments

* **Frontend App (Web, iPad & Android PWA)**:
  👉 **[https://anubhavngm1.github.io/yepigram/](https://anubhavngm1.github.io/yepigram/)**
* **Backend E2EE WebSocket Broker (Render Cloud)**:
  👉 **`https://yapergram.onrender.com`**
  👉 WebSocket endpoint: **`wss://yapergram.onrender.com/ws`**

---

## 📁 Project Architecture

```
yapergram/
├── backend/
│   ├── server.py             # Unified WebSocket & HTTP REST broker
│   ├── database.py           # SQLite zero-knowledge queue & pre-key store
│   ├── requirements.txt      # websockets, aiohttp, cryptography
│   └── Dockerfile            # Production Docker container deployed to Render
├── client/
│   ├── index.html            # Production PWA with 3D liquid glass UI & WebCrypto E2EE
│   ├── manifest.json         # Standalone iPad & Android home screen installation manifest
│   └── sw.js                 # Service worker for offline caching & VAPID Web Push
├── test_e2ee.py              # Automated 10-step cryptographic & queue verification suite
└── README.md                 # Setup and deployment documentation
```

---

## 🚀 Running Locally

```bash
# 1. Run Cryptographic Verification
python test_e2ee.py

# 2. Run Backend
cd backend
python server.py

# 3. Run Client
cd client
python -m http.server 3000
```
