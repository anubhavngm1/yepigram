# Minimal, high-performance production Dockerfile for Yepigram Backend
# Deployable to Koyeb / Render Free Container with zero credit card
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Expose HTTP (8000) and WebSocket (8765)
EXPOSE 8000 8765

CMD ["python", "server.py"]
