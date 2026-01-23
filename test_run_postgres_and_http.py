#!/usr/bin/env python3
import os
import time
import logging
import requests
from sqlalchemy import create_engine, text

LOG = "/tmp/test_run_postgres_and_http.log"
logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def test_db_connection(db_url: str) -> bool:
    logging.info("Testing DB connection to %s", db_url)
    try:
        engine = create_engine(db_url, future=True)
        with engine.connect() as conn:
            val = conn.execute(text("SELECT 1")).scalar()
        logging.info("DB OK: %s", val)
        return True
    except Exception as e:
        logging.error("DB connection failed: %s", e)
        return False

def test_login(base_url: str, user: str, pwd: str) -> bool:
    login_url = f"{base_url}/login"
    session = requests.Session()
    try:
        data = {"username": user, "password": pwd}
        resp = session.post(login_url, data=data, allow_redirects=True, timeout=10)
        logging.info("Login response: %s -> %s", resp.status_code, resp.url)
        return resp.status_code == 200
    except Exception as e:
        logging.error("Login request failed: %s", e)
        return False

def test_moderation_is_up(base_url: str) -> bool:
    url = f"{base_url}/moderation"
    try:
        resp = requests.get(url, timeout=10)
        logging.info("Moderation status: %s", resp.status_code)
        return resp.status_code == 200
    except Exception as e:
        logging.error("Moderation access failed: %s", e)
        return False

def test_media_base(base_url: str) -> bool:
    try:
        resp = requests.head(f"{base_url}/media/test_manual.png", timeout=10)
        logging.info("Media HEAD status: %s", resp.status_code)
        return resp.status_code in (200, 301, 304)
    except Exception as e:
        logging.error("Media HEAD failed: %s", e)
        return False

def main():
    db_url = os.getenv('DATABASE_URL')
    base_url = 'http://localhost:5001'
    user = os.getenv('ADMIN_USERNAME', 'admin')
    pwd = os.getenv('ADMIN_PASSWORD', 'admin123')

    print("Starting tests...")
    ok_db = test_db_connection(db_url) if db_url else False
    ok_login = test_login(base_url, user, pwd) if ok_db else False
    ok_mod = test_moderation_is_up(base_url) if ok_login else False
    ok_media = test_media_base(base_url) if ok_mod else False

    print("Tests result:")
    print(f"DB: {ok_db}")
    print(f"Login: {ok_login}")
    print(f"Moderation: {ok_mod}")
    print(f"Media: {ok_media}")

    with open(LOG, 'a') as f:
        f.write("\nTEST SUMMARY:\n")
        f.write(f"DB: {ok_db}, Login: {ok_login}, Moderation: {ok_mod}, Media: {ok_media}\n")

if __name__ == '__main__':
    main()
