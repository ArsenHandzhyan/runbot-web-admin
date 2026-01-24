"""
Storage Manager for RunBot
Supports Cloudflare R2 (recommended) and Render Disk storage
"""

import os
import logging
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 не установлен. Хранение в R2 недоступно.")

class StorageManager:
    """Управление файлами с поддержкой Cloudflare R2 и Render Disk"""

    def __init__(self):
        self.storage_type = os.getenv('STORAGE_TYPE', 'render_disk')
        self.max_size_mb = int(os.getenv('MAX_UPLOAD_SIZE_MB', '10'))

        logger.info(f"StorageManager initializing: storage_type={self.storage_type}")

        # Ограничения по типам файлов
        self.max_sizes = {
            'image': int(os.getenv('MAX_IMAGE_SIZE_MB', '5')),
            'video': int(os.getenv('MAX_VIDEO_SIZE_MB', '50')),
            'document': int(os.getenv('MAX_DOCUMENT_SIZE_MB', '10'))
        }

        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Настройка R2
            account_id = os.getenv('CLOUDFLARE_R2_ACCOUNT_ID')
            access_key = os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID')
            secret_key = os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY')

            logger.info(f"R2 credential check: account_id={'SET' if account_id else 'NOT SET'}, access_key={'SET' if access_key else 'NOT SET'}, secret_key={'SET' if secret_key else 'NOT SET'}")

            if account_id and access_key and secret_key:
                endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=endpoint_url,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name='auto'
                )
                self.bucket = os.getenv('CLOUDFLARE_R2_BUCKET', 'runbot-media')
                logger.info(f"✅ R2 storage initialized: bucket={self.bucket}, endpoint={endpoint_url}")
            else:
                logger.error(f"❌ R2 credentials not found in environment variables")
                logger.error(f"   Missing: account_id={not account_id}, access_key={not access_key}, secret_key={not secret_key}")
                self.storage_type = 'render_disk'
        elif self.storage_type == 'r2' and not BOTO3_AVAILABLE:
            logger.error("❌ R2 storage requested but boto3 is not available")
            self.storage_type = 'render_disk'

        # Для локального хранения
        if self.storage_type != 'r2' or not BOTO3_AVAILABLE:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.media_path = os.path.join(project_root, 'media')
            os.makedirs(self.media_path, exist_ok=True)
            self.base_url = '/media'
            logger.info(f"✅ Local storage initialized: path={self.media_path}")

    def _detect_file_type(self, filename):
        """Определить тип файла по расширению"""
        ext = filename.lower().split('.')[-1]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            return 'image'
        elif ext in ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm']:
            return 'video'
        elif ext in ['pdf', 'doc', 'docx', 'txt', 'xlsx', 'xls', 'csv']:
            return 'document'
        return 'other'

    def _get_content_type(self, filename):
        """Получить MIME тип файла"""
        ext = filename.lower().split('.')[-1]
        content_types = {
            'txt': 'text/plain',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'csv': 'text/csv',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'mp4': 'video/mp4',
            'avi': 'video/x-msvideo',
            'mov': 'video/quicktime',
            'wmv': 'video/x-ms-wmv',
            'flv': 'video/x-flv',
            'webm': 'video/webm'
        }
        return content_types.get(ext, 'application/octet-stream')

    def validate_file_size(self, file_size_mb, file_type):
        """Проверить размер файла"""
        max_size = self.max_sizes.get(file_type, self.max_size_mb)

        if file_size_mb > max_size:
            return False, f"Файл слишком большой. Максимум: {max_size}MB для {file_type}"

        return True, ""

    def upload_file_from_path(self, file_path, filename=None):
        """Загрузить файл из локального пути в R2 или локальное хранилище"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Определить имя файла
        if filename is None:
            filename = os.path.basename(file_path)

        # Безопасное имя файла
        filename = secure_filename(filename)

        # Проверить размер файла
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)  # MB

        # Определить тип файла
        file_type = self._detect_file_type(filename)

        # Валидация размера
        valid, error_msg = self.validate_file_size(file_size_mb, file_type)
        if not valid:
            logger.error(f"Ошибка валидации файла {filename}: {error_msg}")
            raise ValueError(error_msg)

        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Загрузка в R2
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            r2_filename = f"{timestamp}_{filename}"

            try:
                # Загрузить файл
                with open(file_path, 'rb') as f:
                    self.s3_client.upload_fileobj(
                        f,
                        self.bucket,
                        r2_filename,
                        ExtraArgs={'ContentType': self._get_content_type(filename)}
                    )

                logger.info(f"✅ Файл загружен в R2: {r2_filename} ({file_size_mb:.2f}MB)")

                # Return R2 path format
                return {
                    'path': f"r2://{self.bucket}/{r2_filename}",
                    'url': f"r2://{self.bucket}/{r2_filename}",
                    'size_mb': file_size_mb,
                    'storage_type': 'r2',
                    'filename': r2_filename
                }
            except Exception as e:
                logger.error(f"❌ Failed to upload to R2: {e}")
                # Fallback to local storage
                self.storage_type = 'render_disk'

        # Fallback: Локальное хранение
        import shutil
        dest_path = os.path.join(self.media_path, filename)

        # Only copy if source and destination are different
        if os.path.abspath(file_path) != os.path.abspath(dest_path):
            shutil.copy2(file_path, dest_path)
            logger.info(f"✅ Файл скопирован локально: {dest_path} ({file_size_mb:.2f}MB)")
        else:
            logger.info(f"✅ Файл уже находится в нужном месте: {dest_path} ({file_size_mb:.2f}MB)")

        return {
            'path': dest_path,
            'url': f"{self.base_url}/{filename}",
            'size_mb': file_size_mb,
            'storage_type': 'disk',
            'filename': filename
        }

    def get_file_url(self, file_path, expiration=3600):
        """Получить URL для доступа к файлу (с signed URL для R2)"""
        logger.info(f"get_file_url called: file_path={file_path}, storage_type={self.storage_type}")

        if not file_path:
            logger.warning("get_file_url: file_path is empty")
            return None

        # If it's an R2 path (starts with r2://), generate signed URL
        if file_path.startswith('r2://'):
            logger.info(f"get_file_url: detected R2 path: {file_path}")
            if self.storage_type == 'r2' and BOTO3_AVAILABLE:
                # Extract bucket and key from r2://bucket/key
                parts = file_path.replace('r2://', '').split('/', 1)
                logger.info(f"get_file_url: extracted parts: {parts}")
                if len(parts) == 2:
                    bucket, key = parts
                    logger.info(f"get_file_url: bucket={bucket}, key={key}")
                    try:
                        # Generate presigned URL
                        url = self.s3_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': bucket, 'Key': key},
                            ExpiresIn=expiration
                        )
                        logger.info(f"✅ Generated signed URL for {key}: {url[:100]}...")
                        return url
                    except Exception as e:
                        logger.error(f"❌ Failed to generate signed URL for {file_path}: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"get_file_url: invalid R2 path format, expected 2 parts but got {len(parts)}")
            else:
                logger.warning(f"get_file_url: R2 storage not available (storage_type={self.storage_type}, boto3={BOTO3_AVAILABLE})")
            return None

        # For local files, return direct path
        elif os.path.exists(file_path):
            return f"/media/{os.path.basename(file_path)}"

        return None

    def download_file(self, file_path):
        """Скачать файл из хранилища (возвращает bytes)"""
        logger.info(f"download_file called: file_path={file_path}, storage_type={self.storage_type}")

        if not file_path:
            logger.warning("download_file: file_path is empty")
            return None

        # If it's an R2 path (starts with r2://), download from R2
        if file_path.startswith('r2://'):
            logger.info(f"download_file: detected R2 path: {file_path}")
            if self.storage_type == 'r2' and BOTO3_AVAILABLE:
                # Extract bucket and key from r2://bucket/key
                parts = file_path.replace('r2://', '').split('/', 1)
                logger.info(f"download_file: extracted parts: {parts}")
                if len(parts) == 2:
                    bucket, key = parts
                    logger.info(f"download_file: bucket={bucket}, key={key}")
                    try:
                        # Download file from R2
                        response = self.s3_client.get_object(Bucket=bucket, Key=key)
                        file_data = response['Body'].read()
                        logger.info(f"✅ Downloaded file from R2: {key}, size={len(file_data)} bytes")
                        return file_data
                    except Exception as e:
                        logger.error(f"❌ Failed to download file from R2 {file_path}: {e}", exc_info=True)
                        return None
                else:
                    logger.error(f"download_file: invalid R2 path format, expected 2 parts but got {len(parts)}")
            else:
                logger.warning(f"download_file: R2 storage not available (storage_type={self.storage_type}, boto3={BOTO3_AVAILABLE})")
            return None

        # For local files, read from disk
        elif os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                logger.info(f"✅ Read local file: {file_path}, size={len(file_data)} bytes")
                return file_data
            except Exception as e:
                logger.error(f"❌ Failed to read local file {file_path}: {e}")
                return None

        logger.warning(f"download_file: file not found: {file_path}")
        return None

    def delete_file(self, filepath):
        """Удалить файл"""
        if filepath and filepath.startswith('r2://'):
            if self.storage_type == 'r2' and BOTO3_AVAILABLE:
                # Extract bucket and key
                parts = filepath.replace('r2://', '').split('/', 1)
                if len(parts) == 2:
                    bucket, key = parts
                    try:
                        self.s3_client.delete_object(Bucket=bucket, Key=key)
                        logger.info(f"✅ Файл удалён из R2: {key}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка удаления файла {key}: {e}")
        else:
            # Удалить локально
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"✅ Файл удалён локально: {filepath}")

    def get_storage_stats(self):
        """Получить статистику хранилища"""
        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Статистика R2
            try:
                objects = self.s3_client.list_objects_v2(Bucket=self.bucket)
                total_size = sum(obj['Size'] for obj in objects.get('Contents', []))
                file_count = len(objects.get('Contents', []))

                return {
                    'storage_type': 'r2',
                    'total_size_mb': total_size / (1024 * 1024),
                    'file_count': file_count,
                    'max_size_mb': 10 * 1024,  # 10GB
                    'max_files': int(os.getenv('MAX_TOTAL_FILES', '1000'))
                }
            except Exception as e:
                logger.error(f"Ошибка получения статистики R2: {e}")
                return {
                    'storage_type': 'r2',
                    'total_size_mb': 0,
                    'file_count': 0,
                    'error': str(e)
                }
        else:
            # Локальное хранилище
            total_size = 0
            file_count = 0

            for root, dirs, files in os.walk(self.media_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    if os.path.isfile(filepath):
                        file_count += 1
                        total_size += os.path.getsize(filepath)

            return {
                'storage_type': 'disk',
                'total_size_mb': total_size / (1024 * 1024),
                'file_count': file_count,
                'max_size_mb': 1 * 1024,  # 1GB для Render Disk
                'max_files': int(os.getenv('MAX_TOTAL_FILES', '1000'))
            }

# Глобальный экземпляр для повторного использования
storage_manager = None

def get_storage_manager():
    """Получить глобальный экземпляр StorageManager"""
    global storage_manager
    if storage_manager is None:
        storage_manager = StorageManager()
    return storage_manager
