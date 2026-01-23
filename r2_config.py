"""
Cloudflare R2 Configuration
This file contains R2 storage credentials for the RunBot application.
"""

# Cloudflare R2 Configuration
R2_ACCESS_KEY_ID = "your_r2_access_key_id_here"
R2_SECRET_ACCESS_KEY = "your_r2_secret_access_key_here"
R2_ACCOUNT_ID = "your_r2_account_id_here"
R2_BUCKET_NAME = "runbot-media"
R2_REGION = "auto"  # Cloudflare R2 uses 'auto'

# Storage settings
STORAGE_TYPE = "r2"  # 'r2' or 'render_disk'
MAX_UPLOAD_SIZE_MB = 10
MAX_FILES_PER_USER = 5
MAX_TOTAL_FILES = 1000

# File type limits
MAX_IMAGE_SIZE_MB = 5
MAX_VIDEO_SIZE_MB = 50
MAX_DOCUMENT_SIZE_MB = 10

# Auto cleanup settings
AUTO_CLEANUP_DAYS = 7