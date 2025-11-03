# FastAPI Template

A production-ready FastAPI template with complete CI/CD pipeline, testing, and deployment configurations.

## 🚀 Features

- FastAPI 0.116.2 with Python 3.12
- Async SQLAlchemy (SQLite for dev/test, PostgreSQL for production)
- Alembic migrations
- Pytest with async fixtures
- Ruff (linting) + Black (formatting)
- GitHub Actions CI/CD with Docker
- Multi-stage Dockerfile with Gunicorn + Uvicorn workers

## 🏃 Quick Start

### Development

```bash
# Clone and setup
git clone <repository-url>
cd fast-api-template
cp .env.example.dev .env

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

API available at:
- http://localhost:8000
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/redoc (ReDoc)

## 🐳 Docker

```bash
# Build
docker build -t fastapi-template .

# Run (see .env.example.prod for required variables)
docker run -d -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e POSTGRES_USER=your_user \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_HOST=your_host \
  -e POSTGRES_DB=your_database \
  fastapi-template
```

> **Note**: `.env.example.prod` is a reference template showing which environment variables need to be passed to Docker at runtime. It's not used directly by the application.

## 📡 API Endpoints

- `GET /` - Hello World
- `GET /health` - Health check with DB status
- `GET /docs` - Interactive API docs (Swagger)
- `GET /redoc` - Alternative API docs

## 🗄️ Database

**Development**: SQLite (default, no config needed)

**Production**: Set environment variables:
```bash
ENVIRONMENT=production
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=your_host
POSTGRES_PORT=5432
POSTGRES_DB=your_database
```

## 🧪 Development Commands

```bash
# Tests
pytest
pytest --cov=src --cov-report=html

# Linting
ruff check src/ tests/
ruff check --fix src/ tests/

# Formatting
black src/ tests/

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

## 🏗️ Project Structure

```
fast-api-template/
├── alembic/              # Database migrations
├── .github/workflows/    # CI/CD pipelines
├── src/                  # Application code
│   ├── main.py          # FastAPI app
│   ├── config.py        # Settings
│   └── database.py      # DB setup
├── tests/               # Test suite
├── .env.example.dev     # Dev env template (copy to .env)
├── .env.example.prod    # Reference: Docker env vars for production
├── Dockerfile           # Production image
└── requirements.txt     # Dependencies
```

## 🔄 CI/CD

GitHub Actions pipeline includes:
- Lint (Ruff)
- Test (pytest)
- Build verification
- Coverage reporting
- Docker build & push (on `main` branch)

**Codecov (optional)**: To enable Codecov upload, add the `CODECOV_TOKEN` secret in GitHub settings (Settings → Secrets → Actions). Otherwise, coverage reports are still available as GitHub Actions artifacts. 
