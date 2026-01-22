# Автоматическая настройка проекта для Render с бесплатным хранилищем

## Бесплатные варианты хранения

### 1. Render Disk (Простой, но ограниченный)
- **Бесплатно**: 1GB постоянного хранилища
- **Плюсы**: Работает "из коробки", нет дополнительной настройки
- **Минусы**: При переразвертывании данные могут быть затерты, мало места

### 2. Cloudflare R2 (Рекомендуемый, 10GB бесплатно)
- **Бесплатно**: 10GB хранилища + 10GB трафика в месяц
- **Плюсы**: Данные сохраняются между деплоями, высокая скорость, CDN
- **Минусы**: Требует настройка ключей доступа

### 3. Backblaze B2 (10GB бесплатно + 1GB в день бэкапов)
- **Бесплатно**: 10GB хранилища
- **Плюсы**: Совместим с S3, надёжный
- **Минусы**: Нужно оплачивать бэкапы сверх лимита

## Рекомендация: Cloudflare R2

**Почему R2:**
- 10GB бесплатно (достаточно для медиа файлов проекта)
- Минимальная цена сверх лимита ($0.015/GB/месяц)
- Интеграция CDN бесплатно
- Высокая скорость и доступность
- Данные сохраняются между деплоями

## Автоматическая настройка

### Шаг 1: Создание R2 бакета

```bash
# Установить wrangler (CLI Cloudflare)
npm install -g wrangler

# Авторизоваться
wrangler login

# Создать бакет
wrangler r2 bucket create runbot-media

# Получить ключи доступа
wrangler r2 bucket list
```

### Шаг 2: Настройка переменных окружения на Render

Добавить в Render Dashboard → Environment:

```env
# Хранилище файлов
CLOUDFLARE_R2_ACCESS_KEY_ID=ваш_access_key_id
CLOUDFLARE_R2_SECRET_ACCESS_KEY=ваш_secret_access_key
CLOUDFLARE_R2_BUCKET=runbot-media
CLOUDFLARE_R2_ACCOUNT_ID=ваш_account_id

# Или для Render Disk
MEDIA_PATH=/opt/render/project/data/media

# Ограничения файлов (бесплатный план)
MAX_UPLOAD_SIZE_MB=10
MAX_FILES_PER_USER=5
MAX_TOTAL_FILES=1000
```

### Шаг 3: Обновление кода для работы с R2

```python
# src/utils/storage.py - модуль для работы с хранилищем
import os
import boto3
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

class StorageManager:
    """Управление файлами с поддержкой Cloudflare R2 и Render Disk"""

    def __init__(self):
        self.storage_type = os.getenv('STORAGE_TYPE', 'render_disk')  # 'r2' или 'render_disk'
        self.max_size_mb = int(os.getenv('MAX_UPLOAD_SIZE_MB', '10'))
        
        if self.storage_type == 'r2':
            # Настройка R2
            endpoint_url = f"https://{os.getenv('CLOUDFLARE_R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY'),
            )
            self.bucket = os.getenv('CLOUDFLARE_R2_BUCKET')
        else:
            # Render Disk
            self.media_path = os.getenv('MEDIA_PATH', './media')
    
    def upload_file(self, file, filename=None):
        """Загрузить файл"""
        if filename is None:
            filename = secure_filename(file.filename)
        
        # Проверить размер файла
        file.seek(0, os.SEEK_END)
        file_size = file.tell() / (1024 * 1024)  # MB
        
        if file_size > self.max_size_mb:
            raise ValueError(f'Файл слишком большой. Максимум: {self.max_size_mb}MB')
        
        file.seek(0)  # Вернуться в начало
        
        if self.storage_type == 'r2':
            # Загрузка в R2
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            self.s3_client.upload_fileobj(
                file,
                self.bucket,
                filename,
                ExtraArgs={'ContentType': file.content_type}
            )
            
            return {
                'path': f"r2://{self.bucket}/{filename}",
                'url': f"https://{self.bucket}.r2.cloudflarestorage.com/{filename}",
                'size_mb': file_size
            }
        else:
            # Сохранение локально (Render Disk)
            os.makedirs(self.media_path, exist_ok=True)
            filepath = os.path.join(self.media_path, filename)
            file.save(filepath)
            
            return {
                'path': filepath,
                'url': f"/media/{filename}",
                'size_mb': file_size
            }
    
    def get_file_url(self, filename):
        """Получить URL для скачивания"""
        if self.storage_type == 'r2':
            # Генерация временной ссылки (1 час)
            return self.s3_client.generate_presigned_url(
                self.bucket,
                filename,
                ExpiresIn=3600
            )
        else:
            # Локальный файл
            return f"/media/{filename}"
    
    def delete_file(self, filepath):
        """Удалить файл"""
        if self.storage_type == 'r2':
            # Удалить из R2
            filename = filepath.split('/')[-1]
            self.s3_client.delete_object(Bucket=self.bucket, Key=filename)
        else:
            # Удалить локально
            if os.path.exists(filepath):
                os.remove(filepath)

    def cleanup_old_files(self, days=7):
        """Очистить старые файлы"""
        if self.storage_type == 'r2':
            # Получить список файлов
            objects = self.s3_client.list_objects_v2(Bucket=self.bucket)
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for obj in objects.get('Contents', []):
                obj_date = obj['LastModified']
                if obj_date < cutoff_date:
                    print(f"Удаляем старый файл: {obj['Key']}")
                    self.s3_client.delete_object(
                        Bucket=self.bucket,
                        Key=obj['Key']
                    )
```

### Шаг 4: Интеграция в Flask приложение

```python
# src/web/app.py - обновление для работы с StorageManager
from src.utils.storage import StorageManager
from werkzeug.utils import secure_filename

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """API для загрузки файлов"""
    if 'file' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    try:
        storage = StorageManager()
        result = storage.upload_file(file)
        
        return jsonify({
            'success': True,
            'filename': result['path'],
            'url': result['url'],
            'size_mb': result['size_mb']
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        return jsonify({'error': 'Ошибка загрузки файла'}), 500

@app.route('/media/<path:filename>')
def serve_media(filename):
    """Обслуживание медиа файлов"""
    storage = StorageManager()
    
    if storage.storage_type == 'r2':
        # Для R2 - перенаправление на подписанный URL
        url = storage.get_file_url(filename)
        return redirect(url)
    else:
        # Для локального хранилища - отдать файл
        media_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'media')
        return send_from_directory(media_path, filename)

# Добавить автоматическую очистку старых файлов
@app.route('/admin/cleanup', methods=['POST'])
@login_required
def cleanup_old_files():
    """Очистить старые файлы"""
    storage = StorageManager()
    days = int(request.form.get('days', 7))
    
    try:
        storage.cleanup_old_files(days=days)
        flash(f'Удалены файлы старше {days} дней', 'success')
    except Exception as e:
        logger.error(f"Ошибка очистки: {e}")
        flash(f'Ошибка очистки: {e}', 'error')
    
    return redirect(url_for('statistics'))
```

## Ограничения для экономии места

### В .env:
```env
# Ограничения
MAX_UPLOAD_SIZE_MB=10
MAX_FILES_PER_USER=5
MAX_TOTAL_FILES=1000
AUTO_CLEANUP_DAYS=7

# Квоты для разных типов файлов
MAX_IMAGE_SIZE_MB=5
MAX_VIDEO_SIZE_MB=50
MAX_DOCUMENT_SIZE_MB=10
```

### Валидация при загрузке:

```python
def validate_file(file, file_type):
    """Проверить размер файла по типу"""
    max_sizes = {
        'image': int(os.getenv('MAX_IMAGE_SIZE_MB', 5)),
        'video': int(os.getenv('MAX_VIDEO_SIZE_MB', 50)),
        'document': int(os.getenv('MAX_DOCUMENT_SIZE_MB', 10))
    }
    
    if file_type not in max_sizes:
        return False, "Неподдерживаемый тип файла"
    
    file.seek(0, os.SEEK_END)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    
    if size_mb > max_sizes[file_type]:
        return False, f"Файл слишком большой. Максимум: {max_sizes[file_type]}MB для {file_type}"
    
    return True, ""
```

## Обновление requirements.txt

```txt
# Добавить для Cloudflare R2
boto3>=1.26.0

# Или для Render Disk (уже есть)
flask>=2.0.0
```

## Настройка Render

### 1. Добавить переменные окружения

В Render Dashboard → Web Service → Environment:

```env
# Выбор хранилища
STORAGE_TYPE=r2  # или render_disk

# Cloudflare R2 (если выбран R2)
CLOUDFLARE_R2_ACCESS_KEY_ID=ваш_id
CLOUDFLARE_R2_SECRET_ACCESS_KEY=ваш_secret
CLOUDFLARE_R2_ACCOUNT_ID=ваш_account_id
CLOUDFLARE_R2_BUCKET=runbot-media

# Render Disk (если выбран локальное хранилище)
MEDIA_PATH=/opt/render/project/data/media

# Ограничения
MAX_UPLOAD_SIZE_MB=10
MAX_FILES_PER_USER=5
MAX_TOTAL_FILES=1000
AUTO_CLEANUP_DAYS=7
MAX_IMAGE_SIZE_MB=5
MAX_VIDEO_SIZE_MB=50
MAX_DOCUMENT_SIZE_MB=10

# База данных (уже есть)
DATABASE_URL=postgresql://...
```

### 2. Обновить build command (если нужно)

```bash
# Для R2 нужно установить boto3
pip install boto3 && python app.py
```

## Автоматизация деплоя

### Render уже автоматически деплоит при пуше в main:
```bash
# Просто пушить изменения
git push origin main

# Render автоматически:
# 1. Выполняет git pull
# 2. Устанавливает зависимости (pip install)
# 3. Перезапускает приложение
```
 
### Миграция существующих файлов

Перед настройкой нового хранилища перенесите существующие файлы в R2:

```bash
# Установите зависимости
pip install boto3

# Запустите миграцию
python scripts/migrate_media.py migrate

# Скрипт:
# 1. Найдет все файлы в runbot/media
# 2. Загрузит их в Cloudflare R2
# 3. Обновит пути в БД на r2://...
# 4. Покажет статистику миграции
```

**Результат миграции:**
- ✅ Файлы будут храниться в R2 (10GB бесплатно)
- ✅ Пути в БД обновятся на r2://
- ✅ Данные сохранятся между деплоями
- 📊 Статистика миграции будет показана в консоли

### Восстановление файлов из R2 (только для тестов)

```bash
python scripts/migrate_media.py restore

# Предупреждение: Это операция ТОЛЬКО ДЛЯ ТЕСТОВ!
# Будет создано много локальных файлов
```

## Мониторинг использования

### Добавить страницу статистики хранилища:

```python
@app.route('/admin/storage-stats')
@login_required
def storage_stats():
    """Статистика хранилища"""
    storage = StorageManager()
    
    if storage.storage_type == 'r2':
        # Получить статистику R2
        objects = storage.s3_client.list_objects_v2(Bucket=storage.bucket)
        total_size = sum(obj['Size'] for obj in objects.get('Contents', []))
        file_count = len(objects.get('Contents', []))
        
        return render_template('storage_stats.html',
                         total_size_mb=total_size / (1024*1024),
                         file_count=file_count,
                         max_size_mb=10*1024)  # 10GB
    else:
        # Локальное хранилище
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(storage.media_path):
            for file in files:
                file_count += 1
                total_size += os.path.getsize(os.path.join(root, file))
        
        return render_template('storage_stats.html',
                         total_size_mb=total_size / (1024*1024),
                         file_count=file_count,
                         max_size_mb=1*1024)  # 1GB для Render Disk
```

## Проверка работоспособности

```bash
# Локально:
STORAGE_TYPE=r2 python app.py

# На Render после деплоя:
# Автоматически будут использованы переменные окружения
```

## Резюме

1. Создайте бакет Cloudflare R2 (бесплатно 10GB)
2. Добавьте переменные окружения на Render
3. Добавьте boto3 в requirements.txt
4. Обновите код с StorageManager
5. Установите ограничения на размер файлов
6. Пушьте в main - Render автоматически задеплоит
7. При необходимости перенесите старые файлы через migration скрипт

**Итог:**
- Бесплатно до 10GB (R2) или 1GB (Render Disk)
- Автоматический деплой через Git
- Данные сохраняются между деплоями
- Ограничения на размер файлов
- Автоочистка старых файлов
- Статистика использования хранилища
