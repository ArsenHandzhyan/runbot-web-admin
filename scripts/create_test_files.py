#!/usr/bin/env python3
"""
Создание тестовых медиа-файлов для проверки админ-панели
Создаёт реальные файлы разных типов в папке media
"""

import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

def create_test_files():
    """Создать тестовые медиа-файлы"""
    
    media_dir = 'media'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Создаём папку media если её нет
    os.makedirs(media_dir, exist_ok=True)
    
    print("=" * 60)
    print("🎨 Создание тестовых медиа-файлов")
    print("=" * 60)
    print()
    
    # 1. Тестовое изображение
    test_image = f"test_image_{timestamp}.jpg"
    image_path = os.path.join(media_dir, test_image)
    
    # Создаём простое изображение (блок пикселей)
    from PIL import Image as PILImage
    
    try:
        img = PILImage.new('RGB', (800, 600), color='lightblue')
        img.save(image_path, 'JPEG', quality=85)
        print(f"✅ Создано изображение: {test_image}")
    except ImportError:
        # Если PIL не установлен, создаём пустой файл
        with open(image_path, 'wb') as f:
            f.write(b'fake_image_data')
        print(f"⚠️  PIL не установлен, создан пустой файл: {test_image}")
    except Exception as e:
        with open(image_path, 'wb') as f:
            f.write(b'fake_image_data')
        print(f"⚠️  Ошибка создания изображения, создан пустой файл: {e}")
    
    # 2. Тестовое видео (маленькое, для быстроты)
    test_video = f"test_video_{timestamp}.mp4"
    video_path = os.path.join(media_dir, test_video)
    
    # Создаём тестовое видео (простой MP4 заголовок)
    try:
        with open(video_path, 'wb') as f:
            # MP4 box заголовок + пустой трек
            f.write(b'\x00\x00\x00\x00\x20\x66\x74\x79\x70\x34\x6d\x70\x34')
            f.write(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00')
        print(f"✅ Создано видео: {test_video}")
    except Exception as e:
        print(f"❌ Ошибка создания видео: {e}")
        return False
    
    # 3. Текстовый документ
    test_txt = f"test_document_{timestamp}.txt"
    txt_path = os.path.join(media_dir, test_txt)
    
    txt_content = f"""Тестовый документ от {timestamp}

Это тестовый файл для проверки отображения медиа в админ-панели RunBot.

Тип файла: Текстовый документ (.txt)
Создан: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Содержимое:
- Текст для проверки отображения
- Проверка скачивания файлов
- Проверка превью разных форматов

"""
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(txt_content)
    print(f"✅ Создан документ: {test_txt}")
    
    print()
    print("=" * 60)
    print("📋 Созданные файлы:")
    print("=" * 60)
    print(f"📸 {test_image}")
    print(f"🎥 {test_video}")
    print(f"📄 {test_txt}")
    print()
    print("=" * 60)
    print(f"✅ Все файлы созданы в папке: {os.path.abspath(media_dir)}")
    print("=" * 60)
    print()
    print("📝 Следующий шаг:")
    print("   python3 scripts/create_test_files.py --db")
    print()
    print("   Добавит тестовые записи в БД для отображения в админ-панели")
    print()
    
    return True

def create_db_entries():
    """Создать тестовые записи в БД"""
    
    from dotenv import load_dotenv
    load_dotenv()
    
    from src.database.db import DatabaseManager
    from src.models.models import Submission, SubmissionStatus, Participant, Challenge, ChallengeType
    
    media_dir = 'media'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Файлы которые будем добавлять
    test_files = {
        'image': f'test_image_{timestamp}.jpg',
        'video': f'test_video_{timestamp}.mp4',
        'document': f'test_document_{timestamp}.txt'
    }
    
    print("=" * 60)
    print("💾 Создание тестовых записей в БД")
    print("=" * 60)
    print()
    
    # Инициализируем БД
    db_manager = DatabaseManager()
    db = db_manager.get_session()
    
    try:
        # Получаем или создаём тестовых участников
        participant = db.query(Participant).filter_by(telegram_id=123456789).first()
        
        if not participant:
            participant = Participant(
                telegram_id=123456789,
                full_name="Тестовый Участник",
                birth_date=datetime.now(),
                phone="+79001234567",
                distance_type="adult_run",
                start_number="TEST001",
                registration_date=datetime.now(),
                is_active=True
            )
            db.add(participant)
            db.commit()
            print(f"✅ Создан тестовый участник: TEST001")
        
        # Получаем или создаём тестовый челлендж
        challenge = db.query(Challenge).filter_by(name="Тестовый Челлендж").first()
        
        if not challenge:
            challenge = Challenge(
                name="Тестовый Челлендж",
                description="Тестовый челлендж для проверки отображения файлов",
                challenge_type=ChallengeType.RUNNING,
                start_date=datetime.now(),
                end_date=datetime.now().replace(hour=datetime.now().hour + 24),
                is_active=True
            )
            db.add(challenge)
            db.commit()
            print(f"✅ Создан тестовый челлендж: Тестовый Челлендж")
        
        # Создаём тестовые submissions
        submissions_data = [
            {
                'participant_id': participant.id,
                'challenge_id': challenge.id,
                'submission_date': datetime.now(),
                'result_value': 5.0,
                'result_unit': 'км',
                'media_path': f'./media/{test_files["image"]}',
                'comment': 'Тестовое изображение для проверки админ-панели',
                'status': SubmissionStatus.PENDING,
                'moderator_comment': None
            },
            {
                'participant_id': participant.id,
                'challenge_id': challenge.id,
                'submission_date': datetime.now(),
                'result_value': 3.0,
                'result_unit': 'мин',
                'media_path': f'./media/{test_files["video"]}',
                'comment': 'Тестовое видео для проверки админ-панели',
                'status': SubmissionStatus.PENDING,
                'moderator_comment': None
            },
            {
                'participant_id': participant.id,
                'challenge_id': challenge.id,
                'submission_date': datetime.now(),
                'result_value': 1,
                'result_unit': 'страница',
                'media_path': f'./media/{test_files["document"]}',
                'comment': 'Тестовый документ для проверки админ-панели',
                'status': SubmissionStatus.PENDING,
                'moderator_comment': None
            }
        ]
        
        for i, data in enumerate(submissions_data, 1):
            submission = Submission(**data)
            db.add(submission)
            db.commit()
            
            file_type = ['image', 'video', 'document'][i - 1]
            print(f"✅ Создана запись {i}/{len(submissions_data)}: {test_files[file_type]}")
        
        print()
        print("=" * 60)
        print("📊 Итог по созданным записям:")
        print("=" * 60)
        print(f"👤 Участник: {participant.full_name} (ID: {participant.id})")
        print(f"🏆 Челлендж: {challenge.name} (ID: {challenge.id})")
        print(f"📤 Отчётов создано: {len(submissions_data)}")
        print()
        print(f"📸 Изображение: {test_files['image']}")
        print(f"🎥 Видео: {test_files['video']}")
        print(f"📄 Документ: {test_files['document']}")
        print()
        print("=" * 60)
        print("✅ Все тестовые данные созданы!")
        print("=" * 60)
        print()
        print("📝 Теперь можно:")
        print("   1. Перезапустить веб-админ:")
        print("      kill $(cat /tmp/web_admin.pid) 2>/dev/null || true")
        print("      PORT=5001 python3 app.py > /tmp/web_admin.log 2>&1 &")
        print("      echo $! > /tmp/web_admin.pid")
        print()
        print("   2. Перейти на страницу модерации:")
        print("      http://localhost:5001/moderation")
        print()
        print("   3. Проверить что файлы корректно отображаются:")
        print("      - Изображения должны показываться как превью")
        print("      - Видео должны иметь плеер")
        print("      - Документы должны быть доступны для скачивания")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при создании записей: {e}")
        db.rollback()
        return False
        
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Создание тестовых медиа-файлов')
    parser.add_argument('--db', action='store_true',
                       help='Создать записи в БД')
    
    args = parser.parse_args()
    
    if args.db:
        success = create_db_entries()
        sys.exit(0 if success else 1)
    else:
        success = create_test_files()
        sys.exit(0 if success else 1)
