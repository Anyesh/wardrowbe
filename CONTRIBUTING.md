# Contributing to Wardrowbe

Thank you for your interest in contributing to Wardrowbe! This document provides guidelines and information for contributors.

## Code of Conduct

Please be respectful and constructive in all interactions. We welcome contributors of all experience levels.

## How to Contribute

### Reporting Issues

Before creating a new issue:
1. Search existing issues to avoid duplicates
2. Use the issue templates when available
3. Include relevant details:
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Docker version, etc.)
   - Screenshots if applicable

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Write clear commit messages** following conventional commits
3. **Add tests** for new functionality
4. **Update documentation** as needed
5. **Ensure all tests pass** before submitting

## Development Setup

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for frontend development)
- Python 3.11+ (for backend development)
- An AI service (Ollama recommended for development)

### Local Development

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/wardrowbe.git
cd wardrowbe

# Create environment file
cp .env.example .env
# Edit .env with your settings

# Start with hot reload
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run migrations
docker compose exec backend alembic upgrade head
```

### Backend Development

```bash
cd backend

# Create virtual environment (optional, for IDE support)
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run linting
ruff check .
ruff format .
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Run dev server (if not using Docker)
npm run dev

# Run tests
npm test

# Check types
npm run typecheck

# Run linting
npm run lint
```

## Code Style

### Python (Backend)

- Follow PEP 8
- Use type hints
- Use async/await for database operations
- Keep functions focused and small
- Write docstrings for public functions

```python
async def get_item_by_id(
    self,
    item_id: UUID,
    user_id: UUID,
) -> Optional[ClothingItem]:
    """
    Get a clothing item by ID for a specific user.

    Args:
        item_id: The item's unique identifier
        user_id: The user's unique identifier

    Returns:
        The clothing item if found, None otherwise
    """
    ...
```

### TypeScript (Frontend)

- Use TypeScript strict mode
- Prefer functional components with hooks
- Use React Query for server state
- Follow the existing component patterns

```typescript
interface ItemCardProps {
  item: ClothingItem;
  onSelect?: (item: ClothingItem) => void;
}

export function ItemCard({ item, onSelect }: ItemCardProps) {
  // ...
}
```

## Internationalization

Wardrowbe ships in 8 languages. **Every user-visible string must go through `next-intl`.** A PR that
hardcodes English will be blocked by CI.

Translation files live in `frontend/messages/<locale>/<namespace>.json`, split by feature area.
`en` is the source of truth; every other locale must have exactly the same key set.

```typescript
import { useTranslations } from 'next-intl';

export function ItemCard({ item }: ItemCardProps) {
  const t = useTranslations('wardrobe');
  const tc = useTranslations('common');

  return (
    <div>
      <h3>{t('card.title')}</h3>
      <p>{t('card.wornCount', { count: item.wear_count })}</p>
      <button aria-label={tc('delete')}>{tc('delete')}</button>
    </div>
  );
}
```

Rules:

- Add new keys to `frontend/messages/en/<namespace>.json` only. Other locales are filled in by
  translators; an untranslated key falls back to its English text rather than breaking the page.
- Reuse `common` for generic UI verbs (save, cancel, delete, loading) and `constants` for domain
  vocabulary (clothing types, colors, occasions). Do not re-declare them in a feature namespace.
- Never build a sentence by concatenating fragments around a value. Use one ICU message:
  `t('feelsLike', { temp })`, not `Feels {temp}`.
- Use ICU plurals for anything count-dependent:
  `"itemCount": "{count, plural, one {{count} item} other {{count} items}}"`.
- `placeholder`, `title`, `aria-label`, `alt` and every `toast.*()` argument are user-visible too.

Before pushing:

```bash
cd frontend
npm run i18n:check
```

That runs three gates, none of which `tsc`, ESLint or Vitest can replace, because `t()` takes a
plain string and a missing key type-checks perfectly:

| Gate | Catches |
|------|---------|
| `i18n:keys` | `t()` calls referencing keys absent from the `en` catalog |
| `i18n:parity` | locales missing keys, or ICU placeholders dropped in translation |
| `i18n:scan` | hardcoded user-visible strings in JSX, attributes and toasts |

Adding a language: add it to `SUPPORTED_LOCALES` in `frontend/lib/i18n/locales.ts`, add the same
list to `backend/app/utils/locale.py`, and create `frontend/messages/<locale>/`.

## Project Structure

### Backend

```
backend/
├── app/
│   ├── api/           # API route handlers
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic
│   ├── workers/       # Background job handlers
│   └── utils/         # Shared utilities
├── migrations/        # Alembic migrations
└── tests/            # Test files
```

### Frontend

```
frontend/
├── app/              # Next.js App Router pages
├── components/       # React components
│   └── ui/          # shadcn/ui components
├── lib/             # Utilities and API client
│   └── hooks/       # Custom React hooks
└── tests/           # Test files
```

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_items.py

# Run specific test
pytest tests/test_items.py::TestItemList::test_list_items_empty
```

### Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run in watch mode
npm run test -- --watch
```

## Database Migrations

When modifying models:

```bash
# Create a new migration
docker compose exec backend alembic revision -m "description"

# Apply migrations
docker compose exec backend alembic upgrade head

# Rollback one migration
docker compose exec backend alembic downgrade -1
```

## Pull Request Process

1. Ensure your code follows the style guidelines
2. Update documentation for any changed functionality
3. Add or update tests as appropriate
4. Ensure all CI checks pass
5. Request review from maintainers
6. Address review feedback promptly

### PR Title Format

Use conventional commit format:
- `feat: add outfit sharing functionality`
- `fix: resolve duplicate detection issue`
- `docs: update API documentation`
- `refactor: simplify item service`
- `test: add user preference tests`

## Questions?

If you have questions about contributing, feel free to:
- Open a discussion
- Ask in an existing related issue
- Reach out to maintainers

Thank you for contributing!
