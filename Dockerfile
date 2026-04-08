FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 (whisper 로컬 사용 시 ffmpeg 필요)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
