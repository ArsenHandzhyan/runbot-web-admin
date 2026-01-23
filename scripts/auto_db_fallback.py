#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime

LOG_FILE = "/tmp/db_fallback.log"
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")

def log(msg: str):
    print(msg)
    logging.info(msg)

def test_postgres_connection(dsn: str) -> bool:
    try:
        import psycopg2
        # Use a short timeout to avoid long hangs
        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.close()
        return True
    except Exception as e:
        logging.exception("Не удалось подключиться к Postgres: %s", e)
        return False

def main():
    # Try to load environment variables from .env for local development
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("Loaded .env for local dev (if available)")
    except Exception:
        pass
    log("=== DB Fallback Checker ===")
    # Прочитать DSN из окружения или из .env (DATABASE_URL)
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        log("DATABASE_URL не установлен; пропуск проверки Postgres.")
        # По умолчанию считаем, что можно использовать sqlite для локалки
        return 0

    log(f"Проверяем доступность Postgres: {dsn}")
    ok = test_postgres_connection(dsn)
    if ok:
        log("Postgres доступен. Никакие изменения не требуются.")
        return 0
    else:
        # Фоллбек на SQLite
        sqlite_url = "sqlite:///./dev.db"
        log(f"Postgres недоступен. Перекладываю БД на SQLite: {sqlite_url}")
        # Обновим .env файл, заменив DATABASE_URL на sqlite URL
        env_path = os.path.join(os.getcwd(), '.env')
        if not os.path.exists(env_path):
            # Если .env ещё не создан, создадим минимальный
            with open(env_path, 'w') as f:
                f.write("DATABASE_URL=" + sqlite_url + "\n")
        else:
            # читаем файл построчно и заменяем первую строку с DATABASE_URL
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            replaced = False
            for i, line in enumerate(lines):
                if line.strip().startswith("DATABASE_URL="):
                    lines[i] = f"DATABASE_URL={sqlite_url}\n"
                    replaced = True
                    break
            if not replaced:
                lines.append("DATABASE_URL=" + sqlite_url + "\n")
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        log("Обновление .env выполнено. Запустите приложение снова.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
