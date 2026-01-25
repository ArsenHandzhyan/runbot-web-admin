# RunBot Web Admin Environment Variables

# База данных (общая с ботом)
DATABASE_URL=postgresql://runbot:MMJntms3At5ydvbRcyv1x3l5Yq8dgSUR@dpg-d5maq1f5r7bs73d13c30-a.frankfurt-postgres.render.com/runbot_tp8c

# Admin Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password-in-production
WEB_SECRET_KEY=change-this-secret-key-in-production

# Хранилище файлов
# Тип: 'render_disk' (1GB бесплатно) или 'r2' (10GB бесплатно, рекомендуемый)
STORAGE_TYPE=r2

# Для Render Disk (если STORAGE_TYPE=render_disk)
MEDIA_PATH=./media

# Для Cloudflare R2 (если STORAGE_TYPE=r2)
CLOUDFLARE_R2_ACCOUNT_ID=5075df75a40c529b865d4688f9180d7a
CLOUDFLARE_R2_ACCESS_KEY_ID=y48ae5268b728f8f5950aa8eb0f8439a2
CLOUDFLARE_R2_SECRET_ACCESS_KEY=a73023af18d492d518b7f4b664a1da8ea8ccdaad0ac04ea9fb12ab91194a1a93
CLOUDFLARE_R2_BUCKET=runbot-media
CLOUDFLARE_R2_TOKEN=NJMGcFgc0oDdXABhs_-oZ85r8ZfF7ad2RAyYc5zu
CLOUDFLARE_R2_USE=https://5075df75a40c529b865d4688f9180d7a.eu.r2.cloudflarestorage.com

# Telegram Bot Token (для бота, не нужен для веб-интерфейса)
TELEGRAM_BOT_TOKEN=8193773558:AAHG432pYIeHm34ROF4er2J

# Ограничения файлов (для экономии места)
MAX_UPLOAD_SIZE_MB=10
MAX_IMAGE_SIZE_MB=5
MAX_VIDEO_SIZE_MB=50
MAX_DOCUMENT_SIZE_MB=10
MAX_FILES_PER_USER=5
MAX_TOTAL_FILES=1000

# Автоочистка старых файлов
AUTO_CLEANUP_DAYS=7

# Настройки сервера
PORT=5000
FLASK_DEBUG=True  # Отключить в продакшне
