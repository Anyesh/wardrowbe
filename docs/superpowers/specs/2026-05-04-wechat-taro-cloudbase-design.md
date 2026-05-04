# WeChat Taro Miniapp And CloudBase Backend Design

Date: 2026-05-04

## Goal

Add a WeChat mini program frontend with Taro React that closely matches the current mobile Web product, while keeping the FastAPI/PostgreSQL/Redis backend architecture and adapting it for Tencent CloudBase / WeChat Cloud Hosting where appropriate.

The first production-shaped version should let a WeChat mini program user browse their wardrobe, upload clothing photos, view item details, generate outfit suggestions, review outfits, and edit core settings using the existing backend API contract as much as possible.

## Confirmed Direction

- Build a new Taro React TypeScript app under `miniapp/`.
- Reuse portable Web code where it is genuinely runtime-neutral: types, constants, temperature helpers, data-shaping logic, and API path conventions.
- Rewrite platform-bound code: Next.js routing, NextAuth, Radix/shadcn components, browser `fetch`, `FormData`, `File`, DOM dialogs, and `next/image`.
- Keep the existing FastAPI backend as the core service.
- Deploy the backend as a CloudBase / WeChat Cloud Hosting container, not as a cloud-function rewrite.
- Use CloudBase resources selectively: WeChat mini program container calls, cloud storage for images, and WeChat identity integration.

## Product Scope

### Taro Mini Program Pages

The mini program mirrors the current Web mobile bottom-nav flow:

- `pages/home/index`: dashboard summary, weather, pending outfits, next scheduled outfit, quick actions, insights.
- `pages/wardrobe/index`: two-column item grid, search, filters, sort, processing/error badges, empty states.
- `pages/wardrobe/detail`: item image carousel, tags, favorite toggle, wash/wear actions, edit basics, delete.
- `pages/wardrobe/add`: camera/gallery upload, optional item metadata, upload progress.
- `pages/suggest/index`: weather context, occasion chips, weather override, outfit generation.
- `pages/suggest/result`: generated outfit cards, reasoning/highlights/style notes, accept/reject/try another.
- `pages/outfits/index`: outfit list, search, filter chips, light calendar view.
- `pages/settings/index`: API/backend environment display, account status, location, temperature unit, style preferences.

### Interactions To Preserve

- Bottom tab navigation: Home, Wardrobe, Suggest, Outfits, Settings.
- Photo-first wardrobe grid with status overlays for AI analysis.
- Outfit generation flow: choose occasion, optionally override weather, generate, accept/reject/try another.
- Detail-first item management: favorite, edit tags, mark washed, log wear, remove/delete.
- Loading, error, offline, and empty states should match the current Web tone and behavior.

## Frontend Architecture

### Directory Shape

```text
miniapp/
  package.json
  project.config.json
  config/
  src/
    app.config.ts
    app.ts
    app.scss
    pages/
    components/
    services/
    shared/
```

### Reuse Strategy

Create or copy a small shared layer into `miniapp/src/shared`:

- `types.ts`: adapted from `frontend/lib/types.ts`.
- `temperature.ts`: copied from `frontend/lib/temperature.ts` if it has no DOM/Next dependencies.
- `format.ts`: selected pure formatting helpers from `frontend/lib/utils.ts`.
- `constants.ts`: clothing colors, clothing types, occasions.

Do not import directly from `frontend/` in the first implementation. Direct cross-package imports would require TypeScript path, bundler, and runtime hygiene work before the behavior is proven. After the mini program stabilizes, shared code can be moved into a workspace package.

### API Layer

The Taro API client should expose the same high-level operations used by Web hooks:

- `getItems`, `getItem`, `createItem`, `updateItem`, `deleteItem`, `reanalyzeItem`
- `getWeather`, `getPreferences`, `updatePreferences`, `getUserProfile`, `updateUserProfile`
- `suggestOutfit`, `getOutfits`, `getOutfit`, `acceptOutfit`, `rejectOutfit`, `submitFeedback`
- `getAnalyticsSummary`, `getPendingOutfits`, `getSchedules`

For WeChat runtime:

- Prefer `wx.cloud.callContainer` / `Taro.cloud.callContainer` when CloudBase environment/service config is present.
- Fall back to HTTPS `Taro.request` for local development and non-WeChat targets.
- Use `Taro.uploadFile` for image upload to the backend `/api/v1/items` endpoint.
- Persist auth/session config in Taro storage.

## Backend Architecture

### Keep

Keep the core backend design:

- FastAPI API surface under `/api/v1`.
- SQLAlchemy models and service layer.
- PostgreSQL as the primary relational database.
- Redis for cache, locks, and arq queues.
- Existing AI tagging, recommendation, weather, notification, learning, and pairing services.

### Adapt For CloudBase

#### Cloud Hosting

Run FastAPI as a single CloudBase/WeChat Cloud Hosting service:

- Use an image deployment path, because the backend already has a Dockerfile and native/image dependencies.
- Expose one HTTP port only.
- Configure environment variables in CloudBase service settings.
- Set CloudBase min instances according to worker strategy. API can scale horizontally; worker should be handled separately.

#### Storage

Current backend stores images under `settings.storage_path` on the local filesystem. This conflicts with Cloud Hosting stateless requirements.

Introduce an image storage abstraction:

```python
class ImageStorage:
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get_bytes(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def signed_url(self, key: str) -> str: ...
```

Implement:

- `LocalImageStorage` for existing Docker/local deployments.
- `CloudBaseImageStorage` for CloudBase cloud storage.

Image processing can still use Pillow in memory. Operations that currently require a filesystem path, such as AI preprocessing and background removal, should either read bytes from storage into a temp file for the duration of a request/job or accept bytes directly.

#### Identity

Replace the temporary manual-token miniapp plan with WeChat identity:

- Add a miniapp auth endpoint, e.g. `POST /api/v1/auth/wechat-miniapp/sync`.
- The mini program obtains login credentials via WeChat/CloudBase identity and sends trusted identity data through the cloud container path.
- Backend maps WeChat `openid` or CloudBase UID to `User.external_id`.
- Backend returns the same JWT access token shape currently used by Web.

This preserves the existing `get_current_user` dependency and minimizes changes to downstream APIs.

#### Worker And Async Jobs

Current background work uses Redis/arq:

- AI image tagging.
- notification delivery/retry.
- scheduled outfit checks.
- wash reminders.
- learning profile updates.
- stale processing recovery.

Do not run these as implicit background threads in the API process. Keep a separate worker service or a dedicated always-on worker deployment. If deployed on Cloud Hosting, the worker service must not use low-cost scale-to-zero mode.

## Tencent Cloud Support Matrix

### Directly Supported

- Containerized Python/FastAPI backend. CloudBase documentation lists Python and FastAPI-compatible containerized services as supported.
- HTTP API services and mini program access through cloud container calls.
- VPC access to external resources such as Redis and PostgreSQL when configured.
- Cloud storage for image objects and CDN-backed file delivery.
- Multiple deployment methods including image/Git/CLI deployment.

### Supported With Adaptation

- Existing FastAPI service: supported as a container, but must listen on one HTTP port and be configured through environment variables.
- PostgreSQL: Cloud Hosting can access PostgreSQL through VPC, but CloudBase's built-in database product is MySQL/NoSQL, not a drop-in PostgreSQL replacement.
- Redis/arq: Redis must be an external managed Redis or TencentDB Redis instance. Cloud Hosting must not be used to host Redis itself.
- Local image processing: Pillow processing is fine, but persistent source/thumbnail storage must move out of the container filesystem.
- AI tagging jobs: supported only if executed by a stable worker/service setup, not as fire-and-forget background work in a request handler.
- Scheduled jobs: supported only with an always-on worker or an external scheduler hitting explicit endpoints. Scale-to-zero can terminate long jobs.

### Explicitly Unsupported Or Not Safe To Rely On

These are the parts that Tencent CloudBase/WeChat Cloud Hosting does not support directly or that conflict with its documented operating model:

- Docker Compose deployment. Current `docker-compose.yml` and `docker-compose.prod.yml` cannot be deployed as-is.
- Hosting PostgreSQL or Redis inside Cloud Hosting. Cloud Hosting explicitly does not support deploying databases/Redis as stateful services.
- Permanent local filesystem state. Cloud Hosting services must be stateless and cannot rely on local files surviving across instances, revisions, or scaling events.
- Multiple listening ports in one service. The backend service must expose a single HTTP port.
- Non-HTTP protocols for the backend service. Cloud Hosting supports HTTP service access, not arbitrary tcp/udp/mqtt service exposure.
- Public IP access to Cloud Hosting services. Access is through service domains/container calls, not a stable public IP.
- Background threads or long asynchronous tasks launched outside request lifecycle. Cloud Hosting may scale down or recycle instances and terminate those tasks.
- Low-cost scale-to-zero for worker/cron behavior. Timers and long-running arq jobs require min instances greater than zero or a separate scheduler/worker arrangement.
- Direct migration from PostgreSQL-specific schema to CloudBase MySQL without a compatibility project. The current models use PostgreSQL-specific `JSONB`, `ARRAY`, and UUID patterns, so this is out of scope for the first miniapp/backend adaptation.
- Direct reuse of Next.js/Radix/shadcn UI code in Taro. Taro React runs against mini program components and APIs, not the browser DOM.

## Deployment Model

### Development

- Existing Docker Compose remains the recommended local backend stack.
- Taro miniapp runs against local HTTPS/tunnel or a staging CloudBase service.
- Manual token mode may remain as a developer-only fallback behind explicit debug config.

### Staging/Production

- `api` Cloud Hosting service: FastAPI app.
- `worker` Cloud Hosting service or alternative always-on worker runtime: arq worker.
- Managed PostgreSQL: existing PostgreSQL-compatible service reachable from CloudBase VPC.
- Managed Redis: TencentDB Redis or compatible Redis reachable from CloudBase VPC.
- CloudBase cloud storage: item images, thumbnails, medium images.
- Mini program: Taro WeChat build, configured with CloudBase environment ID and service name.

## Migration Plan

1. Add Taro miniapp shell and shared portable types/constants.
2. Implement Taro API client with HTTP fallback and CloudBase container transport.
3. Add miniapp auth sync endpoint and user mapping.
4. Introduce storage adapter interface and local implementation without behavior change.
5. Add CloudBase storage implementation and switch image URL signing to storage adapter.
6. Adjust AI tagging to work from storage bytes/temp files rather than persistent local paths.
7. Split CloudBase deployment config for API service and worker service.
8. Build the five miniapp flows against existing APIs.
9. Verify local Web remains unaffected.
10. Verify miniapp flows in WeChat Developer Tools and staging CloudBase.

## Testing Strategy

- Backend unit tests for auth sync, storage adapter behavior, URL generation, upload processing, and worker image loading.
- Existing backend test suite must continue passing with local storage.
- Add focused tests that simulate CloudBase storage with an in-memory/fake adapter.
- Taro service-layer tests for API parameter construction and response normalization.
- Manual WeChat Developer Tools QA for tab navigation, upload, image display, outfit suggestion, and auth persistence.

## Out Of Scope

- Full PostgreSQL to CloudBase MySQL migration.
- Full BaaS rewrite to Cloud Functions and CloudBase database.
- Replacing existing Web Next.js frontend.
- Native WeChat payment, subscriptions, or message templates.
- Pixel-perfect reuse of Radix/shadcn components in Taro.

## Open Implementation Questions

- Which exact CloudBase environment ID and Cloud Hosting service name should be used for staging and production?
- Which managed PostgreSQL and Redis products will be reachable from CloudBase VPC?
- Should notification jobs stay enabled in the miniapp deployment, or should the first CloudBase release disable notification workers?
- Should background removal continue to use local `rembg`, or only the existing HTTP provider in CloudBase to reduce image size and cold start cost?

## Sources

- CloudBase cloud hosting overview: https://docs.cloudbase.net/run/introduction
- CloudBase Python cloud hosting quick start: https://docs.cloudbase.net/run/quick-start/dockerize-python
- CloudBase Run deployment limits: https://cloud.tencent.cn/document/product/1243/49235
- CloudBase Run service development notes: https://cloud.tencent.com/document/product/1243/53551
- CloudBase cloud storage overview: https://docs.cloudbase.net/storage/introduce
- CloudBase authentication overview: https://docs.cloudbase.net/authentication-v2/auth/introduce
- Taro mini program CloudBase template: https://docs.taro.zone/docs/wxcloudbase
