FROM python:3.11-slim

WORKDIR /app

# Copy requirements from the backend folder (paths relative to repo root)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from the backend folder
COPY backend/app/ ./app/

# Railway injects PORT at runtime — default to 8080
ENV PORT=8080
EXPOSE 8080

# Start uvicorn using the shell-injected PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
