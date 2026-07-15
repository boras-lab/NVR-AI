FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose ports for various services
# Auth: 8001, Camera: 8002, Stream: 8003, Event: 8004, Telegram: 8005

CMD ["uvicorn", "auth_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
