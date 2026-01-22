#!/usr/bin/env python3
"""
Автоматическая настройка Cloudflare R2
Создание бакета, получение ключей и настройка .env файла
"""

import os
import subprocess
import sys

def run_command(cmd, description=""):
    """Выполнить команду"""
    print(f"🔧 {description}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Ошибка: {result.stderr}")
        return False, None
    return True, result.stdout

def setup_cloudflare_r2():
    """Настроить Cloudflare R2"""
    print("=" * 60)
    print("🚀 Автоматическая настройка Cloudflare R2")
    print("=" * 60)
    print()
    
    # Проверяем наличие npm
    print("📋 Проверяем инструменты...")
    success, output = run_command("which npm", "Проверяем npm")
    
    if not success:
        print("❌ npm не найден. Установите Node.js и npm:")
        print("   brew install node")
        return False
    
    print("✅ npm найден")
    
    # Проверяем wrangler
    success, output = run_command("npm list -g wrangler", "Проверяем wrangler")
    
    if not success or "wrangler" not in output:
        print("📦 Устанавливаем wrangler...")
        success, _ = run_command("npm install -g wrangler", "Установка wrangler")
        if not success:
            return False
        print("✅ wrangler установлен")
    else:
        print("✅ wrangler уже установлен")
    
    print()
    print("🔐 Шаг 1: Создание R2 бакета")
    print("-" * 60)
    
    bucket_name = "runbot-media"
    success, output = run_command(f"wrangler r2 bucket create {bucket_name}", 
                                f"Создание бакета {bucket_name}")
    
    if not success:
        print(f"❌ Не удалось создать бакет. Возможно, он уже существует.")
        print(f"   Попробуйте: wrangler r2 bucket create {bucket_name} --unique")
        return False
    
    print(f"✅ Бакет {bucket_name} создан")
    
    print()
    print("🔑 Шаг 2: Получение ключей доступа")
    print("-" * 60)
    
    success, output = run_command("wrangler r2 bucket list", "Получение списка бакетов")
    
    if not success:
        print("❌ Не удалось получить список бакетов")
        return False
    
    print("📋 Список бакетов:")
    print(output)
    print()
    print("📝 Следующие шаги:")
    print()
    print("1. Перейдите в Cloudflare Dashboard:")
    print("   https://dash.cloudflare.com/")
    print()
    print("2. Найдите ваш бакет:")
    print(f"   {bucket_name}")
    print()
    print("3. Получите ключи доступа:")
    print("   R2 → Manage R2 API Tokens")
    print("   Создайте токен с правами: Object Read & Write")
    print()
    print("4. Вставьте ключи в .env.example.r2:")
    print()
    print("   CLOUDFLARE_R2_ACCOUNT_ID=ваш_account_id")
    print("   CLOUDFLARE_R2_ACCESS_KEY_ID=ваш_access_key_id")
    print("   CLOUDFLARE_R2_SECRET_ACCESS_KEY=ваш_secret_access_key")
    print()
    print("5. Скопируйте .env.example.r2 в .env:")
    print("   cp .env.example.r2 .env")
    print()
    print("6. Запустите миграцию файлов:")
    print("   python scripts/migrate_media.py migrate")
    print()
    
    return True

def install_dependencies():
    """Установить все зависимости проекта"""
    print("=" * 60)
    print("📦 Установка зависимостей")
    print("=" * 60)
    print()
    
    # Установим boto3 если нужно
    success, _ = run_command("pip3 show boto3", "Проверяем boto3")
    
    if not success:
        print("📦 Устанавливаем boto3...")
        success, _ = run_command("pip3 install boto3", "Установка boto3")
        if not success:
            return False
        print("✅ boto3 установлен")
    else:
        print("✅ boto3 уже установлен")
    
    # Установим все зависимости из requirements.txt
    print()
    print("📦 Установка зависимостей из requirements.txt...")
    success, _ = run_command("pip3 install -r requirements.txt", 
                           "Установка зависимостей")
    
    if not success:
        print("❌ Не удалось установить зависимости")
        return False
    
    print("✅ Все зависимости установлены")
    return True

def create_env_file():
    """Создать .env файл из примера"""
    print()
    print("=" * 60)
    print("📝 Создание .env файла")
    print("=" * 60)
    print()
    
    if os.path.exists(".env"):
        print("⚠️  .env файл уже существует")
        print("   Файл НЕ будет перезаписан для сохранения ваших ключей")
        print("   Если хотите перезаписать, удалите .env и запустите снова")
        print()
        return True
    
    # Проверяем наличие .env.example.r2
    if not os.path.exists(".env.example.r2"):
        print("❌ .env.example.r2 не найден")
        return False
    
    # Копируем пример
    import shutil
    shutil.copy(".env.example.r2", ".env")
    print("✅ .env файл создан из .env.example.r2")
    print()
    print("📝 Отредактируйте .env и добавьте ключи Cloudflare:")
    print("   CLOUDFLARE_R2_ACCOUNT_ID")
    print("   CLOUDFLARE_R2_ACCESS_KEY_ID")
    print("   CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    print()
    
    return True

def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Автоматическая настройка RunBot с Cloudflare R2')
    parser.add_argument('--full', action='store_true', 
                       help='Полная настройка: зависимости + Cloudflare R2 + .env')
    parser.add_argument('--cloudflare', action='store_true',
                       help='Только настройка Cloudflare R2')
    parser.add_argument('--deps', action='store_true',
                       help='Только установка зависимостей')
    parser.add_argument('--env', action='store_true',
                       help='Только создание .env файла')
    
    args = parser.parse_args()
    
    if args.full:
        # Полная настройка
        if not install_dependencies():
            sys.exit(1)
        
        if not setup_cloudflare_r2():
            sys.exit(1)
        
        if not create_env_file():
            sys.exit(1)
        
        print()
        print("=" * 60)
        print("🎉 Полная настройка завершена!")
        print("=" * 60)
        print()
        print("📝 Остальные шаги:")
        print("1. Получите ключи Cloudflare R2 из Dashboard")
        print("2. Добавьте ключи в .env файл")
        print("3. Запустите миграцию файлов:")
        print("   python scripts/migrate_media.py migrate")
        print()
    
    elif args.cloudflare:
        # Только Cloudflare
        if not setup_cloudflare_r2():
            sys.exit(1)
    
    elif args.deps:
        # Только зависимости
        if not install_dependencies():
            sys.exit(1)
    
    elif args.env:
        # Только .env
        if not create_env_file():
            sys.exit(1)
    
    else:
        # По умолчанию - полная настройка
        print("⚠️  Не указаны параметры. Запускаю полную настройку (--full)")
        print()
        
        if not install_dependencies():
            sys.exit(1)
        
        if not setup_cloudflare_r2():
            sys.exit(1)
        
        if not create_env_file():
            sys.exit(1)
        
        print()
        print("=" * 60)
        print("🎉 Полная настройка завершена!")
        print("=" * 60)
        print()
        print("📝 Остальные шаги:")
        print("1. Получите ключи Cloudflare R2 из Dashboard")
        print("2. Добавьте ключи в .env файл")
        print("3. Запустите миграцию файлов:")
        print("   python scripts/migrate_media.py migrate")
        print()

if __name__ == "__main__":
    main()
