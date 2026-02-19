# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.2.0...wardrowbe-v1.2.1) (2026-02-19)


### 🐛 Bug Fixes

* Add missing test:coverage script to package.json ([43b8dfa](https://github.com/Anyesh/wardrowbe/commit/43b8dfa6a254c4af67e95b1bb3fefee2eac9d0e4))
* add missing URL fields to TypeScript interfaces ([6113dd6](https://github.com/Anyesh/wardrowbe/commit/6113dd6682227d82dc29251ed9a4fc9054047ad6))
* **ci:** Fix backend storage path and update Node.js to 20 ([55cda11](https://github.com/Anyesh/wardrowbe/commit/55cda11c76e03a490d3faa6981f50016bb1ebfde))
* Ensure opensource repo works for new users ([a003dbd](https://github.com/Anyesh/wardrowbe/commit/a003dbd1c65c8917148b00ac007b466fb6e3430a))
* modernize Python type annotations for Ruff linting ([208920b](https://github.com/Anyesh/wardrowbe/commit/208920bb1f60318100584fc12a1732154570461b))
* re-fetch items after update/archive/restore to load relationships ([edfa65c](https://github.com/Anyesh/wardrowbe/commit/edfa65ce5d9516f61b6094554886f7aec0d452f2))
* Resolve all CI quality check failures ([2209cdf](https://github.com/Anyesh/wardrowbe/commit/2209cdf66ff86090b95e583a6d587be429c2b357))
* resolve CI lint/type/test failures from v1.2.0 release ([3568174](https://github.com/Anyesh/wardrowbe/commit/35681741610d8f696665b63ffc2ee15ad6c94fea))
* Resolve lint and format issues ([86799df](https://github.com/Anyesh/wardrowbe/commit/86799df4e116e3ab3ee4fde4da64e9b945263dac))
* Update AccumulatedItem types to match Item interface ([3e85320](https://github.com/Anyesh/wardrowbe/commit/3e853208a9b2abd99489415d77c923216825689a))


### 📝 Documentation

* improve setup instructions and fix dev mode ([3b567de](https://github.com/Anyesh/wardrowbe/commit/3b567de06f49c5fbe04bfbc04c58ccbf3d743d69))


### 🔧 Maintenance

* add git-blame-ignore-revs for formatting commits ([38fcc6f](https://github.com/Anyesh/wardrowbe/commit/38fcc6f210089bfd0e2bb7979fbfc26487974ba5))
* Add pre-commit hooks for lint/format enforcement ([90343d3](https://github.com/Anyesh/wardrowbe/commit/90343d39fbfd413bf6bbce273d7c7d5b205ba2cc))
* Add tsbuildinfo to gitignore ([b5280aa](https://github.com/Anyesh/wardrowbe/commit/b5280aa158a3eb9228e712444ec62fef918b094e))
* fix linting errors and add missing type properties ([f1c4848](https://github.com/Anyesh/wardrowbe/commit/f1c484883d766961410977de1a81837679a8630f))
* **release:** Add example screens ([2add224](https://github.com/Anyesh/wardrowbe/commit/2add2242a1342de29777fcb4ae74068bb6c8aab1))


### 💄 Styling

* Update README badges to for-the-badge style ([#10](https://github.com/Anyesh/wardrowbe/issues/10)) ([6eff9e9](https://github.com/Anyesh/wardrowbe/commit/6eff9e9278a424ff49e1a9b1d93b5611eb05e123))

## [Unreleased]

### Added

### Changed

### Fixed

## [1.2.0] - 2026-02-06

### Added
- **Wash Tracking** — Track when items need washing based on wear count
  - Per-item configurable wash intervals (or smart defaults by clothing type, e.g. jeans every 6 wears, t-shirts every wear)
  - Visual wash status indicator with progress bar in item detail
  - "Mark as Washed" button to reset the counter
  - Full wash history log with method and notes
  - `needs_wash` filter in the wardrobe to quickly find dirty clothes
  - Background worker sends consolidated laundry reminder notifications every 6 hours via ntfy
- **Multi-Image Support** — Upload up to 4 additional photos per clothing item
  - Image gallery with carousel navigation in item detail dialog
  - Thumbnail strip for quick image switching
  - Set any additional image as the new primary image (swaps them)
  - Add/delete additional images while editing
- **Family Outfit Ratings** — Rate and comment on family members' outfits
  - Star rating (1–5) with optional comment
  - Family Feed page to browse other members' outfits and leave ratings
  - Ratings displayed on outfit history cards and preview dialogs
  - Average family rating shown on outfit cards
  - Family Feed link added to sidebar, mobile nav, and dashboard
- **Wear Statistics** — Detailed per-item wear analytics
  - Total wears, days since last worn, average wears per month
  - Wear-by-month mini bar chart (last 6 months)
  - Wear-by-day-of-week breakdown
  - Most common occasion detection
  - Wear timeline with outfit context (which items were worn together)
- **Wardrobe Sorting & Filtering** — More control over how items are displayed
  - Sort by: newest, oldest, recently worn, least recently worn, most/least worn, name A–Z/Z–A
  - Filter by: needs wash, favorites
  - Collapsible filter bar with active filter count badge
  - "Clear filters" button
- **Improved Item Navigation** — Click items in outfit views to jump to item detail
  - Outfit suggestion items link to wardrobe detail
  - Outfit preview dialog items link to wardrobe detail
  - History card "wore instead" preview links to item detail
  - Deep-link support via `?item=<id>` URL parameter
- **Smarter AI Recommendations** — AI avoids suggesting items that need washing and recently worn exact outfit combinations
- Signed image URLs for improved security

### Changed
- Wear history endpoint now includes full outfit context (which items were worn together)
- "Wore instead" items now also update wash tracking counters
- Item detail dialog redesigned with image gallery, wash status section, and wear history section
- Forward auth token validation made more lenient (`iat` now optional)

### Fixed
- Ruff linting errors in auth.py and images.py
- AccumulatedItem types to match Item interface
- Analytics page item cards now use signed `thumbnail_url` instead of raw path
- Token decode error handling improved with catch-all for malformed payloads

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

[Unreleased]: https://github.com/username/wardrowbe/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/username/wardrowbe/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/username/wardrowbe/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/username/wardrowbe/releases/tag/v1.0.0
