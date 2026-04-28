# MyAstro - Deployment Guide

## Prerequisites

- VPS с SSH доступом (reg.ru, Timeweb, Selectel и т.д.)
- Минимум 2GB RAM, 1 vCPU
- OpenAI API ключ (https://platform.openai.com/api-keys)
- Telegram Bot Token (от @BotFather в Telegram)

## Шаг 1: Подключение к серверу

```bash
ssh root@37.140.192.62
```

## Шаг 2: Установка Docker и клонирование проекта

Скопируй и вставь эту команду целиком:

```bash
curl -fsSL https://raw.githubusercontent.com/S1ayerNN/Sl2/feature/myastro-backend-mvp/deploy/setup-server.sh | bash
```

Или вручную:

```bash
# Обновление системы
apt-get update -y && apt-get upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker

# Установка Docker Compose
apt-get install -y docker-compose-plugin git

# Клонирование проекта
mkdir -p /opt/myastro
git clone -b feature/myastro-backend-mvp https://github.com/S1ayerNN/Sl2.git /opt/myastro/backend
cd /opt/myastro/backend
```

## Шаг 3: Настройка конфигурации

```bash
cd /opt/myastro/backend

# Создаем .env из шаблона
cp .env.example .env

# Генерируем случайные секреты (JWT, пароли БД и т.д.)
bash deploy/generate-secrets.sh

# Открываем .env для редактирования
nano .env
```

В `.env` нужно вручную заполнить:

```
OPENAI_API_KEY=sk-ваш-ключ-openai
TELEGRAM_BOT_TOKEN=1234567890:ваш-токен-от-botfather
```

Остальные секреты уже сгенерированы скриптом.

Сохранить в nano: `Ctrl+O`, `Enter`, `Ctrl+X`

## Шаг 4: Запуск

```bash
cd /opt/myastro/backend

# Запуск всех сервисов
docker compose up -d

# Подождать 10 секунд пока БД поднимется
sleep 10

# Применить миграции БД
docker compose exec api alembic upgrade head
```

## Шаг 5: Проверка

```bash
# Проверить что все контейнеры запущены
docker compose ps

# Проверить health check
curl http://localhost/health
```

Ожидаемый ответ:
```json
{"status":"ok","app":"MyAstro","version":"0.1.0"}
```

## Шаг 6: Проверка API docs

Открой в браузере:
```
http://37.140.192.62/docs
```

Там будет Swagger UI со всеми эндпоинтами.

## Полезные команды

```bash
# Посмотреть логи
docker compose logs -f api

# Перезапустить сервис
docker compose restart api

# Остановить все
docker compose down

# Обновить код и перезапустить
cd /opt/myastro/backend
git pull origin feature/myastro-backend-mvp
docker compose up -d --build
docker compose exec api alembic upgrade head
```

## Деплой Telegram бота

```bash
# Клонируем бот
git clone -b feature/myastro-telegram-bot https://github.com/S1ayerNN/Sl3.git /opt/myastro/bot
cd /opt/myastro/bot

# Настройка
cp .env.example .env
nano .env
```

В `.env` бота:
```
TELEGRAM_BOT_TOKEN=тот-же-токен-что-и-в-backend
API_BASE_URL=http://localhost:8000/api/v1
```

Запуск:
```bash
# Установка зависимостей и запуск
apt-get install -y python3 python3-pip python3-venv
python3 -m venv /opt/myastro/bot/venv
source /opt/myastro/bot/venv/bin/activate
pip install -r requirements.txt
nohup python -m bot.main > /var/log/myastro-bot.log 2>&1 &
```

Или через Docker:
```bash
docker build -t myastro-bot .
docker run -d --name myastro-bot --env-file .env --network myastro_default myastro-bot
```

## Troubleshooting

**Docker не запускается:**
```bash
systemctl status docker
journalctl -u docker
```

**API не отвечает:**
```bash
docker compose logs api
```

**БД не подключается:**
```bash
docker compose logs db
docker compose exec db pg_isready -U myastro
```

**Миграции падают:**
```bash
docker compose exec api alembic current
docker compose exec api alembic heads
```
