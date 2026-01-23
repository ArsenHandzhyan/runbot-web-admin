"""Тестовый модуль для проверки отображения медиа файлов через Blueprint"""

import os
from flask import Blueprint, Response

test_media_blueprint = Blueprint('test_media', __name__)

@test_media_blueprint.route('/test_media/<path:filename>')
def test_media_endpoint(filename):
    # Расчёт пути к media относительно корня репозитория
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    media_path = os.path.join(repo_root, 'media')
    file_path = os.path.join(media_path, os.path.basename(filename))

    if not os.path.exists(file_path):
        return "Файл не найден", 404

    with open(file_path, 'rb') as f:
        data = f.read()
    return Response(data, content_type='application/octet-stream')
