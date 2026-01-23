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
        # Try to load from r2_config.py if environment variables are not set
        self._load_config()

        self.storage_type = os.getenv('STORAGE_TYPE', 'render_disk')  # 'r2' или 'render_disk'
        self.max_size_mb = int(os.getenv('MAX_UPLOAD_SIZE_MB', '10'))

        # Ограничения по типам файлов
        self.max_sizes = {
            'image': int(os.getenv('MAX_IMAGE_SIZE_MB', '5')),
            'video': int(os.getenv('MAX_VIDEO_SIZE_MB', '50')),
            'document': int(os.getenv('MAX_DOCUMENT_SIZE_MB', '10'))
        }

    def _load_config(self):
        """Load configuration from r2_config.py if environment variables are not set"""
        try:
            # Check if r2_config.py exists and load it
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'r2_config.py')
            if os.path.exists(config_path):
                import sys
                config_dir = os.path.dirname(config_path)
                if config_dir not in sys.path:
                    sys.path.insert(0, config_dir)

                import r2_config

                # Set environment variables from config if not already set
                env_vars = {
                    'STORAGE_TYPE': getattr(r2_config, 'STORAGE_TYPE', 'render_disk'),
                    'CLOUDFLARE_R2_ACCESS_KEY_ID': getattr(r2_config, 'R2_ACCESS_KEY_ID', ''),
                    'CLOUDFLARE_R2_SECRET_ACCESS_KEY': getattr(r2_config, 'R2_SECRET_ACCESS_KEY', ''),
                    'CLOUDFLARE_R2_ACCOUNT_ID': getattr(r2_config, 'R2_ACCOUNT_ID', ''),
                    'CLOUDFLARE_R2_BUCKET': getattr(r2_config, 'R2_BUCKET_NAME', ''),
                    'MAX_UPLOAD_SIZE_MB': str(getattr(r2_config, 'MAX_UPLOAD_SIZE_MB', 10)),
                    'MAX_IMAGE_SIZE_MB': str(getattr(r2_config, 'MAX_IMAGE_SIZE_MB', 5)),
                    'MAX_VIDEO_SIZE_MB': str(getattr(r2_config, 'MAX_VIDEO_SIZE_MB', 50)),
                    'MAX_DOCUMENT_SIZE_MB': str(getattr(r2_config, 'MAX_DOCUMENT_SIZE_MB', 10)),
                    'MAX_FILES_PER_USER': str(getattr(r2_config, 'MAX_FILES_PER_USER', 5)),
                    'MAX_TOTAL_FILES': str(getattr(r2_config, 'MAX_TOTAL_FILES', 1000)),
                }

                logger.info(f"Loaded config STORAGE_TYPE: {env_vars['STORAGE_TYPE']}...")
                logger.info(f"R2_ACCESS_KEY_ID loaded: {'Yes' if env_vars['CLOUDFLARE_R2_ACCESS_KEY_ID'] else 'No'}")
                logger.info(f"R2_SECRET_ACCESS_KEY loaded: {'Yes' if env_vars['CLOUDFLARE_R2_SECRET_ACCESS_KEY'] else 'No'}")
                logger.info(f"R2_ACCOUNT_ID loaded: {'Yes' if env_vars['CLOUDFLARE_R2_ACCOUNT_ID'] else 'No'}")

                # Only set if not already set
                for key, value in env_vars.items():
                    if not os.getenv(key) and value:
                        os.environ[key] = value
                        logger.info(f"Set env var {key} from config")

                logger.info("Loaded configuration from r2_config.py")
            else:
                logger.info("r2_config.py not found, using environment variables")

        except Exception as e:
            logger.warning(f"Error loading r2_config.py: {e}")
            logger.info("Falling back to environment variables")
        
        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Check if R2 credentials are available
            access_key = os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID')
            secret_key = os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
            account_id = os.getenv('CLOUDFLARE_R2_ACCOUNT_ID')

            if not all([access_key, secret_key, account_id]):
                logger.error("R2 credentials not found in config file or environment variables")
                # Fall back to render_disk
                self.storage_type = 'render_disk'
            else:
                # Настройка R2
                endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=endpoint_url,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                )
                self.bucket = os.getenv('CLOUDFLARE_R2_BUCKET')
                self.base_url = f"https://{self.bucket}.r2.cloudflarestorage.com"
        else:
            # Render Disk или локальная разработка
            # Приоритет: ABSOLUTE_MEDIA_PATH > MEDIA_PATH > ./media
            # Flask ищет media на два уровня выше app.py (project root)
            media_path_from_env = os.getenv('MEDIA_PATH', './media')
            # Используем абсолютный путь к директории app.py, затем один уровень выше (project root)
            project_root = os.path.dirname(os.path.abspath(__file__))
            absolute_media_path = os.path.join(project_root, 'media')
            
            if os.getenv('ABSOLUTE_MEDIA_PATH'):
                self.media_path = os.getenv('ABSOLUTE_MEDIA_PATH')
                logger.info(f"Используется ABSOLUTE_MEDIA_PATH: {self.media_path}")
            else:
                # Для локальной разработки используем абсолютный путь в project_root/media
                # При деплое на Render, MEDIA_PATH можно задать как /opt/render/project/data/media
                self.media_path = absolute_media_path
                logger.info(f"Используется путь: {self.media_path}")
            
            self.base_url = '/media'
        
        logger.info(f"StorageManager инициализирован: {self.storage_type}, media_path: {self.media_path}")
    
    def _detect_file_type(self, filename):
        """Определить тип файла"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            return 'image'
        elif ext in ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm']:
            return 'video'
        elif ext in ['pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx']:
            return 'document'
        else:
            return 'other'
    
    def validate_file_size(self, file_size_mb, file_type):
        """Проверить размер файла"""
        max_size = self.max_sizes.get(file_type, self.max_size_mb)
        
        if file_size > max_size:
            return False, f"Файл слишком большой. Максимум: {max_size}MB для {file_type}"
        if file_size > self.max_size_mb:
            return False, f"Файл слишком большой. Максимум: {self.max_size_mb}MB"
        
        return True, ""
    
    def upload_file(self, file, filename=None):
        """Загрузить файл"""
        if filename is None:
            filename = secure_filename(file.filename)
        
        # Проверить размер файла
        file.seek(0, os.SEEK_END)
        file_size_mb = file.tell() / (1024 * 1024)  # MB
        file.seek(0)
        
        # Определить тип файла
        file_type = self._detect_file_type(filename)
        
        # Валидация размера
        valid, error_msg = self.validate_file_size(file_size_mb, file_type)
        if not valid:
            logger.error(f"Ошибка валидации файла {filename}: {error_msg}")
            raise ValueError(error_msg)
        
        # Проверить общие лимиты
        total_files = os.getenv('MAX_TOTAL_FILES', '1000')
        max_files = os.getenv('MAX_FILES_PER_USER', '5')
        
        if file_size_mb > self.max_size_mb:
            raise ValueError(f'Файл слишком большой. Максимум: {self.max_size_mb}MB')
        
        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Загрузка в R2
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            self.s3_client.upload_fileobj(
                file,
                self.bucket,
                filename,
                ExtraArgs={'ContentType': file.content_type}
            )
            
            logger.info(f"Файл загружен в R2: {filename} ({file_size_mb:.2f}MB)")
            return {
                'path': f"r2://{self.bucket}/{filename}",
                'url': f"{self.base_url}/{filename}",
                'size_mb': file_size_mb,
                'storage_type': 'r2'
            }
        else:
            # Сохранение локально (Render Disk)
            filepath = os.path.join(self.media_path, filename)
            file.save(filepath)
            
            logger.info(f"Файл сохранён локально: {filepath} ({file_size_mb:.2f}MB)")
            return {
                'path': filepath,
                'url': f"{self.base_url}/{filename}",
                'size_mb': file_size_mb,
                'storage_type': 'disk'
            }
    
    def get_file_url(self, filename):
        """Получить URL для скачивания"""
        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Генерация временной ссылки (1 час)
            try:
                url = self.s3_client.generate_presigned_url(
                    self.bucket,
                    filename,
                    ExpiresIn=3600
                )
                return url
            except Exception as e:
                logger.error(f"Ошибка генерации URL для {filename}: {e}")
                return None
        else:
            # Локальный файл
            return f"{self.base_url}/{filename}"
    
    def delete_file(self, filepath):
        """Удалить файл"""
        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Удалить из R2
            filename = filepath.split('/')[-1]
            try:
                self.s3_client.delete_object(
                    Bucket=self.bucket,
                    Key=filename
                )
                logger.info(f"Файл удалён из R2: {filename}")
            except Exception as e:
                logger.error(f"Ошибка удаления файла {filename}: {e}")
        else:
            # Удалить локально
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Файл удалён локально: {filepath}")
    
    def cleanup_old_files(self, days=7):
        """Очистить старые файлы"""
        if self.storage_type == 'r2' and BOTO3_AVAILABLE:
            # Получить список файлов
            try:
                objects = self.s3_client.list_objects_v2(Bucket=self.bucket)
                
                cutoff_date = datetime.now() - timedelta(days=days)
                deleted_count = 0
                
                for obj in objects.get('Contents', []):
                    obj_date = obj['LastModified'].replace(tzinfo=None)
                    if obj_date < cutoff_date:
                        print(f"Удаляем старый файл: {obj['Key']}")
                        self.s3_client.delete_object(
                            Bucket=self.bucket,
                            Key=obj['Key']
                        )
                        deleted_count += 1
                
                logger.info(f"Очистка R2: удалено {deleted_count} файлов старше {days} дней")
                return deleted_count
            except Exception as e:
                logger.error(f"Ошибка очистки R2: {e}")
                return 0
        else:
            # Локальная очистка
            try:
                cutoff_date = datetime.now() - timedelta(days=days)
                deleted_count = 0
                
                for root, dirs, files in os.walk(self.media_path):
                    for file in files:
                        filepath = os.path.join(root, file)
                        file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                        
                        if file_time < cutoff_date:
                            os.remove(filepath)
                            deleted_count += 1
                
                logger.info(f"Очистка диска: удалено {deleted_count} файлов старше {days} дней")
                return deleted_count
            except Exception as e:
                logger.error(f"Ошибка очистки диска: {e}")
                return 0
    
    def upload_file_from_path(self, file_path: str):
        """Legacy method - files should already be uploaded via upload_file()"""
        logger.warning(f"upload_file_from_path called with {file_path} - this method is deprecated")
        logger.warning("Files should be uploaded directly using upload_file() method")
        # This is a no-op - file should already be in correct location
        return file_path

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
