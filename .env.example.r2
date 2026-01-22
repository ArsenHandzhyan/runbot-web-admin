# RunBot Web Admin Environment Variables

# База данных (общая с ботом)
DATABASE_URL=postgresql://user:password@localhost:5432/runbot_db

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
CLOUDFLARE_R2_ACCOUNT_ID=your_account_id
CLOUDFLARE_R2_ACCESS_KEY_ID=your_access_key_id
CLOUDFLARE_R2_SECRET_ACCESS_KEY=your_secret_access_key
CLOUDFLARE_R2_BUCKET=runbot-media

# Telegram Bot Token (для бота, не нужен для веб-интерфейса)
TELEGRAM_BOT_TOKEN=your-bot-token-here

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
