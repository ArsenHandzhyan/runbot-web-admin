# RunBot Web Admin - Standalone Version

Веб-интерфейс администратора RunBot, который может работать независимо от Telegram бота.

## Особенности

- ✅ Полностью независимое веб-приложение
- ✅ Может работать на отдельном сервере
- ✅ Поддерживает те же функции, что и встроенная версия
- ✅ Совместимо с BotHost и другими платформами хостинга

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка окружения

Создайте файл `.env` на основе `.env.web`:

```bash
cp .env.web .env
```

Отредактируйте `.env` файл:
```env
# Обязательные переменные
TELEGRAM_BOT_TOKEN=ваш_токен_бота
ADMIN_USERNAME=ваш_логин
ADMIN_PASSWORD=ваш_пароль
WEB_SECRET_KEY=ваш_секретный_ключ

# Опциональные переменные
DATABASE_URL=postgresql://your-postgres-connection-string
MEDIA_PATH=./media
FLASK_DEBUG=False
AI_WORKER_URL=https://your-ai-worker.onrender.com
AI_WORKER_API_KEY=change_me
```

### 3. Запуск

#### Локальный запуск:
```bash
python app.py
```

#### Запуск с указанием порта:
```bash
PORT=5000 python app.py
```

#### Запуск в режиме отладки:
```bash
FLASK_DEBUG=True python app.py
```

### 4. Доступ к интерфейсу

Откройте в браузере: `http://localhost:5000`

Данные для входа по умолчанию:
- Логин: `admin` 
- Пароль: `aaAA2576525005`

## Деплой на различных платформах

### Heroku
```bash
heroku create your-app-name
heroku config:set TELEGRAM_BOT_TOKEN=ваш_токен
heroku config:set ADMIN_USERNAME=ваш_логин
heroku config:set ADMIN_PASSWORD=ваш_пароль
heroku config:set WEB_SECRET_KEY=ваш_ключ
git push heroku main
```

### Render
1. Создайте Web Service
2. Укажите `app.py` как главный файл
3. Добавьте переменные окружения
4. Деплой автоматически запустится

### DigitalOcean App Platform
1. Создайте App
2. Выберите этот репозиторий
3. Укажите `app.py` как точку входа
4. Настройте переменные окружения

### AWS Elastic Beanstalk
```bash
eb init
eb create runbot-web
eb deploy
```

## Структура проекта

```
runbot-web/
├── app.py              # Главный файл приложения
├── src/                # Исходный код
│   ├── web/           # Веб-компоненты
│   ├── database/      # Работа с БД
│   ├── models/        # Модели данных
│   └── utils/         # Вспомогательные функции
├── templates/          # HTML шаблоны
├── static/            # Статические файлы
├── requirements.txt    # Зависимости
├── .env.web           # Пример конфигурации
└── README.md          # Эта документация
```

## Переменные окружения

| Переменная | Обязательная | Описание |
|------------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Токен Telegram бота |
| `ADMIN_USERNAME` | ✅ | Логин администратора |
| `ADMIN_PASSWORD` | ✅ | Пароль администратора |
| `WEB_SECRET_KEY` | ✅ | Секретный ключ для Flask |
| `DATABASE_URL` | ❌ | URL базы данных (по умолчанию SQLite) |
| `MEDIA_PATH` | ❌ | Путь к медиа файлам |
| `PORT` | ❌ | Порт для запуска (по умолчанию 5000) |
| `FLASK_DEBUG` | ❌ | Режим отладки (True/False) |

## Разработка

### Запуск в режиме разработки:
```bash
FLASK_DEBUG=True python app.py
```

### Тестирование:
```bash
python -m pytest tests/
```

## Поддержка

Если у вас возникли проблемы:
1. Проверьте логи приложения
2. Убедитесь, что все переменные окружения заданы
3. Проверьте доступность базы данных
