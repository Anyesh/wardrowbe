<p align="center">
  <img src="./frontend/public/logo.svg" alt="wardrowbe" width="120" height="120">
</p>

<h1 align="center">wardrowbe</h1>

<p align="center">
  Put your wardrobe in rows. Snap. Organize. Wear.
</p>
<p align="center">
  <a href="https://claude.ai/code"><img src="https://img.shields.io/badge/Built%20with%20Claude%20Code-D97757?style=for-the-badge&logo=claude&logoColor=white" alt="Built with Claude Code"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#contributing">Contributing</a>
</p>


Self-hosted wardrobe management with AI-powered outfit recommendations. Take photos of your clothes, let AI tag them, and get daily outfit suggestions based on weather and occasion.

## Features

- **Photo-based wardrobe** - Upload photos, AI extracts clothing details automatically
- **Smart recommendations** - Outfits matched to weather, occasion, and your preferences
- **Scheduled notifications** - Daily outfit suggestions via ntfy/Mattermost/email
- **Family support** - Manage wardrobes for household members
- **Wear tracking** - History, ratings, and outfit feedback
- **Analytics** - See what you wear, what you don't, color distribution
- **Fully self-hosted** - Your data stays on your hardware
- **Works with any AI** - OpenAI, Ollama, LocalAI, or any OpenAI-compatible API

## Screenshots

### Wardrobe & AI Tagging
| Wardrobe Grid | AI Analysis |
|---------------|-------------|
| ![Wardrobe](screenshots/wardrobe.png) | ![AI Analysis](screenshots/wardrobe-grid.png) |

### Outfit Suggestions & History
| Suggestions | History Calendar |
|-------------|------------------|
| ![Suggest](screenshots/suggest.png) | ![History](screenshots/history.png) |

### Analytics & Pairing
| Analytics | Pairing |
|-----------|---------------|
| ![Analytics](screenshots/analytics.png) | ![Pairing](screenshots/pairings.png) |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An AI service (OpenAI API key, or local Ollama/LocalAI instance)

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/wardrowbe.git
cd wardrowbe

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Start everything
docker compose up -d

# Run database migrations
docker compose exec backend alembic upgrade head
```

Access the app at `http://localhost:3000`

### Development Mode

For hot reloading during development:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## AI Configuration

### Using Ollama (Recommended for Self-Hosting)
You can use separate models for image and text or use multimodal LLM like qwen3-vl, gemma3, etc.

1. Install [Ollama](https://ollama.ai)
2. Pull models:
   ```bash
   ollama pull llava      # Vision model for clothing analysis
   ollama pull llama3     # Text model for recommendations
   ```
3. Configure in `.env`:
   ```
   AI_BASE_URL=http://host.docker.internal:11434/v1
   AI_VISION_MODEL=llava
   AI_TEXT_MODEL=llama3
   ```

### Using OpenAI

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-api-key
AI_VISION_MODEL=gpt-4o
AI_TEXT_MODEL=gpt-4o
```

### Using LocalAI

```env
AI_BASE_URL=http://localai:8080/v1
AI_VISION_MODEL=gpt-4-vision-preview
AI_TEXT_MODEL=gpt-3.5-turbo
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│                   (Next.js + React Query)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                        Backend                               │
│                   (FastAPI + SQLAlchemy)                     │
└──────────┬──────────────┬──────────────────┬────────────────┘
           │              │                  │
    ┌──────▼──────┐ ┌─────▼─────┐    ┌──────▼──────┐
    │  PostgreSQL │ │   Redis   │    │  AI Service │
    │  (Database) │ │ (Job Queue)│   │ (OpenAI/etc)│
    └─────────────┘ └─────┬─────┘    └─────────────┘
                          │
               ┌──────────▼──────────┐
               │   Background Worker │
               │    (arq - AI Jobs)  │
               └─────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, TanStack Query, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, SQLAlchemy (async), Pydantic, Python 3.11+ |
| Database | PostgreSQL 15 |
| Cache/Queue | Redis 7 |
| Background Jobs | arq |
| Authentication | NextAuth.js (supports OIDC, dev credentials) |
| AI | Any OpenAI-compatible API |

## Deployment

### Docker Compose (Production)

See [docker-compose.prod.yml](docker-compose.prod.yml) for production configuration.

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose exec backend alembic upgrade head
```

### Kubernetes

See the [k8s/](k8s/) directory for Kubernetes manifests including:
- PostgreSQL and Redis with persistent storage
- Backend API and worker deployments
- Next.js frontend
- Ingress with TLS
- Network policies

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `SECRET_KEY` | Backend secret for JWT | Yes |
| `NEXTAUTH_SECRET` | NextAuth session encryption | Yes |
| `AI_BASE_URL` | AI service URL | Yes |
| `AI_API_KEY` | AI API key (if required) | Depends |

See [.env.example](.env.example) for all options.

### Authentication

- **Development Mode** (default): Simple email/name login
- **OIDC Mode**: Authentik, Keycloak, Auth0, or any OIDC provider

### Notifications

- **ntfy.sh**: Free push notifications
- **Mattermost**: Team messaging webhook
- **Email**: SMTP-based

### Weather

Uses [Open-Meteo](https://open-meteo.com/) - free, no API key needed.

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt

# Run tests
pytest

# Run with hot reload
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install

# Run dev server
npm run dev

# Run tests
npm test

# Build
npm run build
```

### API Documentation

Available when running:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Requirements

- Docker & Docker Compose
- ~4GB RAM (with local Ollama models)
- Storage for clothing photos

Works great on a Raspberry Pi 5!
