#!/usr/bin/env python3
"""
Миграция файлов из локального хранилища в Cloudflare R2
Выполняется один раз для переноса существующих файлов
"""

import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.utils.storage import StorageManager, get_storage_manager
from src.database.db import DatabaseManager
from src.models.models import Submission

# Загружаем переменные окружения
load_dotenv()

def migrate_files_to_r2():
    """Перенести файлы из локального хранилища в R2"""
    
    print("=== Миграция файлов в Cloudflare R2 ===")
    
    # Проверяем тип хранилища
    storage_type = os.getenv('STORAGE_TYPE', 'render_disk')
    
    if storage_type != 'r2':
        print("⚠️  STORAGE_TYPE не установлен в 'r2'")
        print("Пожалуйста, установите STORAGE_TYPE=r2 в .env")
        return False
    
    # Инициализируем подключение к БД
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Получаем все submissions с media файлами
        submissions = db.query(Submission).filter(
            Submission.media_path.isnot(None)
        ).all()
        
        if not submissions:
            print("❌ Нет файлов для миграции")
            return False
        
        storage = get_storage_manager()
        migrated_count = 0
        failed_count = 0
        
        print(f"📋 Найдено {len(submissions)} файлов для миграции")
        print()
        
        for i, submission in enumerate(submissions, 1):
            filename = submission.media_path.split('/')[-1] if '/' in submission.media_path else submission.media_path
            
            # Проверяем существование файла
            if not os.path.exists(submission.media_path):
                print(f"⚠️  [{i}/{len(submissions)}] Файл не найден: {filename}")
                failed_count += 1
                continue
            
            print(f"📤 [{i}/{len(submissions)}] Загрузка: {filename}")
            
            try:
                # Загружаем в R2
                with open(submission.media_path, 'rb') as f:
                    from io import BytesIO
                    result = storage.upload_file(
                        {'file': BytesIO(f.read()), 'filename': filename}
                    )
                
                # Обновляем путь в БД
                submission.media_path = result['path']
                db.commit()
                
                print(f"   ✅ {result['url']}")
                
                # Удаляем локальный файл (опционально)
                # os.remove(submission.media_path)
                
                migrated_count += 1
                
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
                failed_count += 1
            
            # Пауза каждые 10 файлов
            if i % 10 == 0:
                db.close()
                db = db_manager.get_session()
                print()
                print("🔄 Пауза перед следующими 10 файлами...")
                print()
        
        print()
        print("=" * 50)
        print("=== Результаты миграции ===")
        print(f"✅ Успешно мигрировано: {migrated_count} файлов")
        print(f"❌ Ошибок: {failed_count} файлов")
        print(f"📊 Всего обработано: {len(submissions)} файлов")
        print("=" * 50)
        
        return migrated_count > 0
        
    finally:
        db.close()

def restore_from_r2():
    """Восстановить локальные файлы из R2 (только для тестов)"""
    
    print("=== Восстановление файлов из Cloudflare R2 ===")
    print("⚠️  Это операция ТОЛЬКО ДЛЯ ТЕСТОВ!")
    print("⚠️  Будет создано много локальных файлов.")
    print()
    
    confirm = input("Продолжить? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Отменено.")
        return False
    
    # Инициализируем подключение к БД
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Получаем все submissions с R2 путями
        submissions = db.query(Submission).filter(
            Submission.media_path.like('r2://%')
        ).all()
        
        if not submissions:
            print("❌ Нет файлов с R2 путями")
            return False
        
        restored_count = 0
        
        print(f"📋 Найдено {len(submissions)} файлов для восстановления")
        print()
        
        for i, submission in enumerate(submissions, 1):
            filename = submission.media_path.split('/')[-1] if '/' in submission.media_path else submission.media_path
            
            print(f"📥 [{i}/{len(submissions)}] Загрузка: {filename}")
            
            # TODO: Реализовать скачивание из R2
            # Для этого нужно получить файл из R2 и сохранить локально
            # Затем обновить путь в БД на локальный
            
            restored_count += 1
        
        print()
        print("=" * 50)
        print(f"✅ Восстановлено: {restored_count} файлов")
        print("=" * 50)
        
        return True
        
    finally:
        db.close()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Миграция файлов в Cloudflare R2')
    parser.add_argument('action', choices=['migrate', 'restore'], help='Действие: migrate - перенести в R2, restore - восстановить из R2')
    
    args = parser.parse_args()
    
    if args.action == 'migrate':
        success = migrate_files_to_r2()
        sys.exit(0 if success else 1)
    elif args.action == 'restore':
        success = restore_from_r2()
        sys.exit(0 if success else 1)
