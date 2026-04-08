FROM python:3.11-slim

WORKDIR /app

# whisper_local 전환 시 ffmpeg 필요하므로 유지
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
