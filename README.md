# MyAstro Backend

AI-powered personalized horoscope service backend.

## Tech Stack

- **Framework**: FastAPI (Python 3.12)
- **Database**: PostgreSQL 16 + Redis 7
- **AI**: OpenAI GPT-4o-mini / GPT-4o
- **Auth**: JWT + Telegram Login + Google Sign-In
- **Deploy**: Docker Compose + Nginx

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

### 3. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 4. Access the API

- API docs: http://localhost/docs
- Health check: http://localhost/health

## API Endpoints

### Authentication
- `POST /api/v1/auth/telegram` - Login via Telegram
- `POST /api/v1/auth/google` - Login via Google
- `POST /api/v1/auth/refresh` - Refresh JWT tokens

### Profile
- `GET /api/v1/profile/me` - Get user profile
- `PATCH /api/v1/profile/me` - Update profile
- `GET /api/v1/profile/completeness` - Get profile completeness hints

### Horoscope
- `POST /api/v1/horoscope/generate` - Generate daily horoscope
- `GET /api/v1/horoscope/today` - Get today's horoscope
- `GET /api/v1/horoscope/history` - Get last 5 horoscopes
- `POST /api/v1/horoscope/{id}/feedback` - Submit feedback (like/dislike)

## Project Structure

```
app/
├── api/            # API endpoints (routers)
├── core/           # Config, database, security, Redis
├── models/         # SQLAlchemy ORM models
├── schemas/        # Pydantic request/response schemas
└── services/       # Business logic (AI, auth, horoscope)
```

## Environment Variables

See `.env.example` for all required configuration.
