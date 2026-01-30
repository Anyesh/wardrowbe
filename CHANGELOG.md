# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Signed image URLs for improved security

### Changed

### Fixed
- Ruff linting errors in auth.py and images.py
- AccumulatedItem types to match Item interface

### Removed

## [1.1.0] - 2026-01-30

### Added
- **AI Learning System** - Netflix/Spotify-style recommendation learning that improves over time
  - Learns color preferences from user feedback patterns
  - Tracks item pair compatibility scores based on outfit acceptance
  - Builds user learning profiles with computed style insights
  - Generates actionable style recommendations
- **"Wore Instead" Tracking** - Record what you actually wore when rejecting suggestions to improve future recommendations
- **Learning Insights Dashboard** - View your learned preferences, best item pairs, and AI-generated style insights
- **Outfit Performance Tracking** - Detailed metrics on outfit acceptance rates, ratings, and comfort scores
- Pre-commit hooks for lint/format enforcement

### Fixed
- Backend storage path and updated Node.js to 20
- Added missing test:coverage script to package.json
- Ensure opensource repo works for new users
- Resolved all CI quality check failures

## [1.0.0] - 2026-01-25

### Added
- **Photo-based wardrobe management** - Upload photos with automatic AI-powered clothing analysis
- **Smart outfit recommendations** - AI-generated suggestions based on weather, occasion, and preferences
- **Scheduled notifications** - Daily outfit suggestions via ntfy, Mattermost, or email
- **Family support** - Manage wardrobes for multiple household members
- **Wear tracking** - History, ratings, and outfit feedback system
- **Analytics dashboard** - Visualize wardrobe usage, color distribution, and wearing patterns
- **Outfit calendar** - View and track outfit history by date
- **Pairing system** - AI-generated clothing pairings with feedback learning
- **User preferences** - Customizable style preferences and notification settings
- **Authentication** - Secure user authentication with session management
- **Health checks** - API health monitoring endpoints
- **Docker support** - Full containerization with docker-compose for dev and production
- **Kubernetes manifests** - Production-ready k8s deployment configurations
- **Database migrations** - Alembic-based schema migrations
- **Test suite** - Comprehensive backend and frontend tests

### Technical
- Backend: FastAPI with Python
- Frontend: Next.js with TypeScript
- Database: PostgreSQL with Redis caching
- AI: Compatible with OpenAI, Ollama, LocalAI, or any OpenAI-compatible API
- Reverse proxy: Nginx/Caddy configurations included

[Unreleased]: https://github.com/username/wardrowbe/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/username/wardrowbe/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/username/wardrowbe/releases/tag/v1.0.0
