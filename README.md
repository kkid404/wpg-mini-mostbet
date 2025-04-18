# WPG-Mini (WordPress Generator Mini)

WPG-Mini - это система автоматического развертывания и управления множественными WordPress сайтами. Проект предоставляет API и веб-интерфейс для быстрого создания, настройки и управления WordPress сайтами на разных серверах.

## Функциональные возможности

- **Управление доменами**: добавление, настройка и мониторинг доменов WordPress
- **Управление серверами**: добавление и конфигурация серверов для хостинга сайтов
- **Интеграция с Cloudflare**: автоматическая настройка DNS записей и SSL-сертификатов
- **Автоматическая генерация Apache конфигов**: настройка виртуальных хостов HTTP и HTTPS
- **Установка WordPress**: автоматическая установка и настройка WordPress с плагинами
- **Управление SSL**: создание и обновление Let's Encrypt сертификатов
- **Миграция сайтов**: перенос WordPress сайтов между серверами
- **Управление пользователями**: регистрация, аутентификация и разграничение прав доступа

## Технический стек

- **Backend**: FastAPI, SQLAlchemy, Celery
- **Хранение данных**: PostgreSQL, Redis
- **Безопасность**: JWT авторизация
- **Управление серверами**: Paramiko (SSH)
- **Интеграции**: Cloudflare API, Let's Encrypt (Certbot), Namecheap API

## Установка и запуск

### Предварительные требования

- Python 3.8+
- PostgreSQL
- Redis
- Доступ к серверам (SSH)

### Настройка окружения

1. Клонировать репозиторий и создать виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

2. Установить зависимости:
```bash
pip install -r reqs.txt
```

3. Настроить параметры в config.ini:
```ini
[DATABASE]
host=localhost
port=5432
name=your_db_name
user=your_db_user
pass=your_db_password

[SYSTEM]
secret=your_secret_key
```

4. Инициализировать базу данных:
```bash
alembic upgrade head
```

### Запуск сервисов

1. Запуск API сервера:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. Запуск Celery для фоновых задач:
```bash
celery -A tasks worker --loglevel=info
```

3. Запуск Flower для мониторинга Celery (опционально):
```bash
celery -A tasks flower
```

## Структура проекта

- **modules/** - модули API (domains, servers, cloudflare, auth, и т.д.)
- **tools/** - утилиты для работы с Cloudflare, Certbot, и т.д.
- **migrations/** - миграции базы данных
- **tasks.py** - Celery задачи для фоновых процессов
- **models.py** - ORM модели SQLAlchemy
- **main.py** - основной файл FastAPI приложения

## Использование API

API документация доступна по адресу `/docs` или `/redoc` после запуска приложения.

Основные эндпоинты:
- `/domains` - управление доменами WordPress
- `/servers` - управление серверами
- `/cloudflare` - управление Cloudflare интеграцией
- `/auth` - аутентификация и управление пользователями

## Безопасность

- Пароли пользователей хранятся в хешированном виде
- API запросы защищены JWT токенами
- SSH соединения используют ключи для аутентификации

## Лицензия

Проприетарное программное обеспечение 