"""
Простой тестовый endpoint для проверки медиа файлов
Использует os.listdir() вместо send_from_directory для совместимости
"""

import os
from flask import Flask, Response

app = Flask(__name__)

@app.route('/test_simple/<path:filename>')
def test_simple_endpoint(filename):
    """Простой тестовый endpoint для проверки файлов"""
    try:
        media_dir = 'media'
        
        # Проверяем что filename не содержит попыток выхода из директории
        if '..' in filename or filename.startswith('/'):
            return 'Invalid filename', 400
        
        # Формируем безопасный путь
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(media_dir, safe_filename)
        
        if not os.path.exists(file_path):
            return f"Файл {safe_filename} не найден", 404
        
        # Читаем содержимое файла
        with open(file_path, 'rb') as f:
            content = f.read()
        
        return Response(content, content_type='text/plain')
        
    except Exception as e:
        return f"Ошибка чтения файла: {str(e)}", 500

if __name__ == '__main__':
    app.run(port=5002, debug=True)
