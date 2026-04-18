FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Railway injects PORT dynamically — must use it exactly
ENV PORT=8080
EXPOSE 8080

# Use exec form with shell to correctly expand $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
