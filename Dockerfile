FROM python:3.12-slim

# Müzik için FFmpeg + Opus (ses kanalına konuşmak için) gerekli
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# yt-dlp'yi her başlangıçta güncelle (YouTube sık değiştiği için), sonra botu çalıştır
CMD ["sh", "-c", "pip install -q -U 'yt-dlp[default]' yt-dlp-ejs; exec python -u bot.py"]
