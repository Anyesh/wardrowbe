# WeChat Taro CloudBase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Taro React WeChat mini program that mirrors the current mobile Web flows while adapting the existing FastAPI backend for CloudBase cloud hosting, WeChat identity, and cloud image storage.

**Architecture:** Keep the existing FastAPI/PostgreSQL/Redis backend as the system of record. Add narrow backend adapters for WeChat miniapp auth and image storage, then build a separate `miniapp/` Taro app with a platform API client that calls CloudBase containers in WeChat and HTTPS in local development.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Redis/arq, pytest, Taro React, TypeScript, Sass, Vitest-compatible service tests, CloudBase/WeChat Cloud Hosting.

---

## File Structure

### Backend Files

- Create: `backend/app/services/image_storage.py`
  - Storage interface plus local filesystem implementation.
- Create: `backend/app/services/cloudbase_storage.py`
  - CloudBase cloud storage implementation behind the same interface.
- Modify: `backend/app/config.py`
  - Add storage backend and WeChat/CloudBase configuration fields.
- Modify: `backend/app/services/image_service.py`
  - Use storage adapter for persistent images while keeping Pillow processing.
- Modify: `backend/app/utils/signed_urls.py`
  - Keep local signed API URLs and allow storage-provided public/signed URLs.
- Modify: `backend/app/api/images.py`
  - Serve local images through storage adapter; redirect or proxy CloudBase URLs.
- Modify: `backend/app/api/auth.py`
  - Add miniapp sync endpoint returning the existing `UserSyncResponse`.
- Modify: `backend/app/schemas/user.py`
  - Add request schema for WeChat miniapp auth.
- Modify: `backend/app/workers/tagging.py`
  - Load images through storage/temp files rather than assuming permanent local paths.
- Modify: `backend/app/api/items.py`
  - Enqueue tagging jobs with storage keys, not absolute local paths.
- Create: `backend/tests/test_image_storage.py`
- Create: `backend/tests/test_wechat_auth.py`
- Modify: `backend/tests/test_items.py`
- Modify: `backend/tests/test_ai_service.py`

### Miniapp Files

- Create: `miniapp/package.json`
- Create: `miniapp/project.config.json`
- Create: `miniapp/config/index.ts`
- Create: `miniapp/config/dev.ts`
- Create: `miniapp/config/prod.ts`
- Create: `miniapp/src/app.config.ts`
- Create: `miniapp/src/app.ts`
- Create: `miniapp/src/app.scss`
- Create: `miniapp/src/pages/home/index.tsx`
- Create: `miniapp/src/pages/wardrobe/index.tsx`
- Create: `miniapp/src/pages/wardrobe/detail.tsx`
- Create: `miniapp/src/pages/wardrobe/add.tsx`
- Create: `miniapp/src/pages/suggest/index.tsx`
- Create: `miniapp/src/pages/suggest/result.tsx`
- Create: `miniapp/src/pages/outfits/index.tsx`
- Create: `miniapp/src/pages/settings/index.tsx`
- Create: `miniapp/src/pages/home/index.tsx`
- Create: `miniapp/src/pages/wardrobe/index.tsx`
- Create: `miniapp/src/pages/wardrobe/detail.tsx`
- Create: `miniapp/src/pages/wardrobe/add.tsx`
- Create: `miniapp/src/pages/suggest/index.tsx`
- Create: `miniapp/src/pages/suggest/result.tsx`
- Create: `miniapp/src/pages/outfits/index.tsx`
- Create: `miniapp/src/pages/settings/index.tsx`
- Create: `miniapp/src/shared/types.ts`
- Create: `miniapp/src/shared/constants.ts`
- Create: `miniapp/src/shared/temperature.ts`
- Create: `miniapp/src/shared/format.ts`
- Create: `miniapp/src/services/session.ts`
- Create: `miniapp/src/services/api.ts`
- Create: `miniapp/src/services/items.ts`
- Create: `miniapp/src/services/outfits.ts`
- Create: `miniapp/src/services/user.ts`
- Create: `miniapp/src/components/*`
- Create: `miniapp/src/pages/home/index.tsx`
- Create: `miniapp/src/pages/home/index.scss`
- Create: `miniapp/src/pages/wardrobe/index.tsx`
- Create: `miniapp/src/pages/wardrobe/index.scss`
- Create: `miniapp/src/pages/wardrobe/detail.tsx`
- Create: `miniapp/src/pages/wardrobe/add.tsx`
- Create: `miniapp/src/pages/suggest/index.tsx`
- Create: `miniapp/src/pages/suggest/result.tsx`
- Create: `miniapp/src/pages/outfits/index.tsx`
- Create: `miniapp/src/pages/settings/index.tsx`

### Deployment And Docs

- Create: `cloudbase/api.Dockerfile`
- Create: `cloudbase/worker.Dockerfile`
- Create: `cloudbase/README.md`
- Modify: `README.md`

---

## Task 1: Backend Storage Interface

**Files:**
- Create: `backend/app/services/image_storage.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_image_storage.py`

- [ ] **Step 1: Write failing tests for local storage**

```python
# backend/tests/test_image_storage.py
from pathlib import Path

import pytest

from app.services.image_storage import LocalImageStorage


@pytest.mark.asyncio
async def test_local_storage_put_get_delete(tmp_path: Path):
    storage = LocalImageStorage(tmp_path)

    await storage.put_bytes("user/a.jpg", b"image-bytes", "image/jpeg")

    assert await storage.get_bytes("user/a.jpg") == b"image-bytes"
    assert (tmp_path / "user" / "a.jpg").exists()

    await storage.delete("user/a.jpg")

    assert not (tmp_path / "user" / "a.jpg").exists()


@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal(tmp_path: Path):
    storage = LocalImageStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid storage key"):
        await storage.put_bytes("../escape.jpg", b"x", "image/jpeg")
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest tests/test_image_storage.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.image_storage'`.

- [ ] **Step 3: Implement storage interface and local adapter**

```python
# backend/app/services/image_storage.py
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ImageStorage(ABC):
    @abstractmethod
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def signed_url(self, key: str) -> str | None:
        return None


class LocalImageStorage(ImageStorage):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("Invalid storage key")
        full_path = self.root / key
        resolved = full_path.resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid storage key")
        return full_path

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def get_bytes(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()
```

Add config fields:

```python
# backend/app/config.py
storage_backend: str = Field(default="local")
cloudbase_env_id: str | None = None
cloudbase_storage_bucket: str | None = None
wechat_miniapp_appid: str | None = None
wechat_miniapp_secret: str | None = None
```

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && pytest tests/test_image_storage.py -q`

Expected: PASS.

- [ ] **Step 5: Run existing image-related tests**

Run: `cd backend && pytest tests/test_items.py tests/test_remove_bg_endpoint.py -q`

Expected: PASS or only pre-existing environment skips.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/image_storage.py backend/app/config.py backend/tests/test_image_storage.py
git commit -m "feat: add image storage abstraction"
```

---

## Task 2: Route ImageService Through Storage

**Files:**
- Modify: `backend/app/services/image_service.py`
- Modify: `backend/app/api/images.py`
- Modify: `backend/app/utils/signed_urls.py`
- Test: `backend/tests/test_image_storage.py`

- [ ] **Step 1: Write failing behavior test for processed images stored through adapter**

```python
# append to backend/tests/test_image_storage.py
from io import BytesIO
from PIL import Image

from app.services.image_service import ImageService
from app.services.image_storage import LocalImageStorage


def make_jpeg() -> bytes:
    out = BytesIO()
    Image.new("RGB", (32, 32), "white").save(out, format="JPEG")
    return out.getvalue()


@pytest.mark.asyncio
async def test_image_service_processes_into_storage(tmp_path: Path):
    service = ImageService(storage=LocalImageStorage(tmp_path))

    result = await service.process_and_store(
        user_id="11111111-1111-1111-1111-111111111111",
        image_data=make_jpeg(),
        original_filename="shirt.jpg",
    )

    assert result["image_path"].endswith(".jpg")
    assert await service.storage.get_bytes(result["thumbnail_path"])
```

- [ ] **Step 2: Run test to verify RED**

Run: `cd backend && pytest tests/test_image_storage.py::test_image_service_processes_into_storage -q`

Expected: FAIL because `ImageService.__init__` does not accept `storage`.

- [ ] **Step 3: Update ImageService constructor and writes**

Implement:

```python
# backend/app/services/image_service.py
from app.services.image_storage import ImageStorage, LocalImageStorage

class ImageService:
    def __init__(self, storage_path: str | None = None, storage: ImageStorage | None = None):
        self.storage_path = Path(storage_path or settings.storage_path)
        self.storage = storage or LocalImageStorage(self.storage_path)
```

Replace each `file_path.write_bytes(resized_data)` in `process_and_store` with:

```python
await self.storage.put_bytes(paths[size_name], resized_data, "image/jpeg")
```

Keep `get_image_path()` for legacy local operations in this task.

- [ ] **Step 4: Run storage tests**

Run: `cd backend && pytest tests/test_image_storage.py -q`

Expected: PASS.

- [ ] **Step 5: Run item upload tests**

Run: `cd backend && pytest tests/test_items.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/image_service.py backend/tests/test_image_storage.py
git commit -m "refactor: store processed images through adapter"
```

---

## Task 3: WeChat Miniapp Auth Sync Endpoint

**Files:**
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/api/auth.py`
- Test: `backend/tests/test_wechat_auth.py`

- [ ] **Step 1: Write failing tests for dev-safe miniapp sync**

```python
# backend/tests/test_wechat_auth.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_creates_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={
            "openid": "openid-123",
            "display_name": "Mini User",
            "avatar_url": "https://example.com/a.png",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "openid-123@wechat-miniapp.local"
    assert data["display_name"] == "Mini User"
    assert data["access_token"]


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_requires_identity(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={"display_name": "No ID"},
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest tests/test_wechat_auth.py -q`

Expected: FAIL with 404 for `/api/v1/auth/wechat-miniapp/sync`.

- [ ] **Step 3: Add request schema**

```python
# backend/app/schemas/user.py
class WeChatMiniappSyncRequest(BaseModel):
    openid: str | None = Field(None, min_length=1, max_length=255)
    cloudbase_uid: str | None = Field(None, min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = None
```

- [ ] **Step 4: Add endpoint**

```python
# backend/app/api/auth.py
@router.post("/wechat-miniapp/sync", response_model=UserSyncResponse)
async def sync_wechat_miniapp_user(
    sync_data: WeChatMiniappSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSyncResponse:
    external_subject = sync_data.cloudbase_uid or sync_data.openid
    if not external_subject:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="openid or cloudbase_uid is required",
        )

    external_id = f"wechat-miniapp:{external_subject}"
    email = f"{external_subject}@wechat-miniapp.local"
    user_service = UserService(db)
    user, is_new = await user_service.sync_from_oidc(
        UserSyncRequest(
            external_id=external_id,
            email=email,
            display_name=sync_data.display_name or "WeChat User",
            avatar_url=sync_data.avatar_url,
            provider="wechat-miniapp",
        )
    )
    return UserSyncResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_new_user=is_new,
        onboarding_completed=user.onboarding_completed,
        access_token=create_access_token(user.external_id),
    )
```

Import `WeChatMiniappSyncRequest` and `UserSyncRequest`.

- [ ] **Step 5: Run auth tests**

Run: `cd backend && pytest tests/test_wechat_auth.py tests/test_auth.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/user.py backend/app/api/auth.py backend/tests/test_wechat_auth.py
git commit -m "feat: add wechat miniapp auth sync"
```

---

## Task 4: Worker Uses Storage Keys Safely

**Files:**
- Modify: `backend/app/api/items.py`
- Modify: `backend/app/workers/tagging.py`
- Test: `backend/tests/test_items.py`

- [ ] **Step 1: Write failing test for enqueue payload**

Add a test that monkeypatches `redis.enqueue_job` and asserts the third argument is a storage key like `user/file.jpg`, not `/data/wardrobe/user/file.jpg`.

```python
async def test_create_item_enqueues_storage_key(client, monkeypatch):
    enqueued = {}

    class FakeRedis:
        async def enqueue_job(self, name, item_id, image_key, _queue_name):
            enqueued["name"] = name
            enqueued["image_key"] = image_key

        async def aclose(self):
            pass

    async def fake_create_pool(*args, **kwargs):
        return FakeRedis()

    monkeypatch.setattr("app.api.items.create_pool", fake_create_pool)
    # Build a valid image upload the same way existing item tests do.
    # After POST /api/v1/items, assert:
    # assert not enqueued["image_key"].startswith("/")
```

- [ ] **Step 2: Run test to verify RED**

Run: `cd backend && pytest tests/test_items.py::test_create_item_enqueues_storage_key -q`

Expected: FAIL because current code builds `f"{settings.storage_path}/{image_paths['image_path']}"`.

- [ ] **Step 3: Enqueue storage key**

In `backend/app/api/items.py`, replace enqueue calls like:

```python
full_image_path = f"{settings.storage_path}/{image_paths['image_path']}"
await redis.enqueue_job("tag_item_image", str(item.id), full_image_path, _queue_name="arq:tagging")
```

with:

```python
await redis.enqueue_job(
    "tag_item_image",
    str(item.id),
    image_paths["image_path"],
    _queue_name="arq:tagging",
)
```

- [ ] **Step 4: Adapt worker to materialize temp file**

In `backend/app/workers/tagging.py`, replace direct `Path(image_path)` validation with:

```python
from tempfile import NamedTemporaryFile
from app.services.image_service import ImageService

image_service = ImageService()
image_bytes = await image_service.storage.get_bytes(image_path)
with NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
    tmp.write(image_bytes)
    tmp.flush()
    tags = await ai_service.analyze_image(Path(tmp.name))
```

Keep error handling so missing storage keys mark the item as `error`.

- [ ] **Step 5: Run backend tests**

Run: `cd backend && pytest tests/test_items.py tests/test_ai_service.py tests/test_worker_db.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/items.py backend/app/workers/tagging.py backend/tests/test_items.py
git commit -m "refactor: enqueue image storage keys for tagging"
```

---

## Task 5: CloudBase Storage Adapter Skeleton

**Files:**
- Create: `backend/app/services/cloudbase_storage.py`
- Modify: `backend/app/services/image_storage.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_image_storage.py`

- [ ] **Step 1: Write failing factory test**

```python
from app.services.image_storage import get_image_storage


def test_get_image_storage_returns_local_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    storage = get_image_storage()

    assert storage.__class__.__name__ == "LocalImageStorage"


def test_get_image_storage_rejects_cloudbase_without_bucket(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "cloudbase")
    monkeypatch.delenv("CLOUDBASE_STORAGE_BUCKET", raising=False)

    with pytest.raises(RuntimeError, match="CLOUDBASE_STORAGE_BUCKET"):
        get_image_storage()
```

- [ ] **Step 2: Run test to verify RED**

Run: `cd backend && pytest tests/test_image_storage.py::test_get_image_storage_returns_local_by_default tests/test_image_storage.py::test_get_image_storage_rejects_cloudbase_without_bucket -q`

Expected: FAIL because `get_image_storage` is missing.

- [ ] **Step 3: Add CloudBase adapter skeleton and factory**

```python
# backend/app/services/cloudbase_storage.py
from app.services.image_storage import ImageStorage


class CloudBaseImageStorage(ImageStorage):
    def __init__(self, bucket: str, env_id: str | None = None):
        self.bucket = bucket
        self.env_id = env_id

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError("CloudBase SDK upload will be implemented with deployment credentials")

    async def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError("CloudBase SDK download will be implemented with deployment credentials")

    async def delete(self, key: str) -> None:
        raise NotImplementedError("CloudBase SDK delete will be implemented with deployment credentials")
```

```python
# backend/app/services/image_storage.py
from app.config import get_settings


def get_image_storage() -> ImageStorage:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalImageStorage(settings.storage_path)
    if settings.storage_backend == "cloudbase":
        if not settings.cloudbase_storage_bucket:
            raise RuntimeError("CLOUDBASE_STORAGE_BUCKET is required for cloudbase storage")
        from app.services.cloudbase_storage import CloudBaseImageStorage

        return CloudBaseImageStorage(settings.cloudbase_storage_bucket, settings.cloudbase_env_id)
    raise RuntimeError(f"Unsupported STORAGE_BACKEND: {settings.storage_backend}")
```

- [ ] **Step 4: Wire ImageService default to factory**

Change constructor default:

```python
self.storage = storage or get_image_storage()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_image_storage.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/cloudbase_storage.py backend/app/services/image_storage.py backend/app/services/image_service.py backend/tests/test_image_storage.py
git commit -m "feat: add cloudbase storage factory"
```

---

## Task 6: Taro Project Shell

**Files:**
- Create: `miniapp/package.json`
- Create: `miniapp/project.config.json`
- Create: `miniapp/config/index.ts`
- Create: `miniapp/config/dev.ts`
- Create: `miniapp/config/prod.ts`
- Create: `miniapp/src/app.config.ts`
- Create: `miniapp/src/app.ts`
- Create: `miniapp/src/app.scss`

- [ ] **Step 1: Create Taro package manifest**

```json
{
  "name": "wardrowbe-miniapp",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev:weapp": "taro build --type weapp --watch",
    "build:weapp": "taro build --type weapp",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@tarojs/components": "^4.0.0",
    "@tarojs/helper": "^4.0.0",
    "@tarojs/plugin-framework-react": "^4.0.0",
    "@tarojs/plugin-platform-weapp": "^4.0.0",
    "@tarojs/react": "^4.0.0",
    "@tarojs/runtime": "^4.0.0",
    "@tarojs/taro": "^4.0.0",
    "react": "18.2.0"
  },
  "devDependencies": {
    "@tarojs/cli": "^4.0.0",
    "@types/react": "18.2.52",
    "typescript": "5.3.3"
  }
}
```

- [ ] **Step 2: Add app config with tabBar**

```ts
// miniapp/src/app.config.ts
export default defineAppConfig({
  pages: [
    'pages/home/index',
    'pages/wardrobe/index',
    'pages/wardrobe/detail',
    'pages/wardrobe/add',
    'pages/suggest/index',
    'pages/suggest/result',
    'pages/outfits/index',
    'pages/settings/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'wardrowbe',
    navigationBarTextStyle: 'black',
  },
  tabBar: {
    color: '#6b7280',
    selectedColor: '#111827',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/home/index', text: 'Home' },
      { pagePath: 'pages/wardrobe/index', text: 'Wardrobe' },
      { pagePath: 'pages/suggest/index', text: 'Suggest' },
      { pagePath: 'pages/outfits/index', text: 'Outfits' },
      { pagePath: 'pages/settings/index', text: 'Settings' },
    ],
  },
})
```

- [ ] **Step 3: Add global app component and styles**

```tsx
// miniapp/src/app.ts
import React from 'react'
import './app.scss'

export default function App({ children }: { children: React.ReactNode }) {
  return children
}
```

```scss
/* miniapp/src/app.scss */
page {
  min-height: 100%;
  background: #ffffff;
  color: #111827;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.page {
  min-height: 100vh;
  padding: 24rpx;
  box-sizing: border-box;
}
```

- [ ] **Step 4: Add minimal page shells for configured routes**

Create each configured route with this shape, changing the title per page:

```tsx
// miniapp/src/pages/home/index.tsx
import { View, Text } from '@tarojs/components'

export default function HomePage() {
  return (
    <View className='page'>
      <Text>Home</Text>
    </View>
  )
}
```

- [ ] **Step 5: Run install and typecheck**

Run: `cd miniapp && npm install && npm run typecheck`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add miniapp/package.json miniapp/package-lock.json miniapp/project.config.json miniapp/config miniapp/src/app.config.ts miniapp/src/app.ts miniapp/src/app.scss miniapp/src/pages
git commit -m "feat: scaffold taro miniapp"
```

---

## Task 7: Miniapp Shared Types And API Client

**Files:**
- Create: `miniapp/src/shared/types.ts`
- Create: `miniapp/src/shared/constants.ts`
- Create: `miniapp/src/shared/temperature.ts`
- Create: `miniapp/src/shared/format.ts`
- Create: `miniapp/src/services/session.ts`
- Create: `miniapp/src/services/api.ts`

- [ ] **Step 1: Copy portable shared code**

Use `frontend/lib/types.ts` and `frontend/lib/temperature.ts` as source material. Keep only the interfaces/constants used by miniapp pages in the first pass: items, outfits, weather, preferences, user profile, colors, clothing types, occasions.

- [ ] **Step 2: Add session service**

```ts
// miniapp/src/services/session.ts
import Taro from '@tarojs/taro'

const TOKEN_KEY = 'wardrowbe_access_token'
const API_BASE_KEY = 'wardrowbe_api_base_url'

export function getAccessToken(): string {
  return Taro.getStorageSync(TOKEN_KEY) || ''
}

export function setAccessToken(token: string): void {
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function getApiBaseUrl(): string {
  return Taro.getStorageSync(API_BASE_KEY) || ''
}

export function setApiBaseUrl(url: string): void {
  Taro.setStorageSync(API_BASE_KEY, url.replace(/\/$/, ''))
}
```

- [ ] **Step 3: Add transport client**

```ts
// miniapp/src/services/api.ts
import Taro from '@tarojs/taro'
import { getAccessToken, getApiBaseUrl } from './session'

export interface ApiOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data?: unknown
  params?: Record<string, string | number | boolean | undefined>
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public data: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

function buildQuery(params?: ApiOptions['params']): string {
  if (!params) return ''
  const pairs = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  return pairs.length ? `?${pairs.join('&')}` : ''
}

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const token = getAccessToken()
  const baseUrl = getApiBaseUrl()
  const url = `${baseUrl}/api/v1${path}${buildQuery(options.params)}`
  const response = await Taro.request({
    url,
    method: options.method || 'GET',
    data: options.data,
    header: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (response.statusCode < 200 || response.statusCode >= 300) {
    const data = response.data as { detail?: string } | undefined
    throw new ApiError(response.statusCode, data?.detail || 'Request failed', response.data)
  }

  return response.data as T
}
```

- [ ] **Step 4: Typecheck**

Run: `cd miniapp && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add miniapp/src/shared miniapp/src/services/session.ts miniapp/src/services/api.ts
git commit -m "feat: add miniapp shared types and api client"
```

---

## Task 8: Miniapp Domain Services

**Files:**
- Create: `miniapp/src/services/items.ts`
- Create: `miniapp/src/services/outfits.ts`
- Create: `miniapp/src/services/user.ts`

- [ ] **Step 1: Add item service**

```ts
// miniapp/src/services/items.ts
import Taro from '@tarojs/taro'
import { apiRequest } from './api'
import { getAccessToken, getApiBaseUrl } from './session'
import type { Item, ItemFilter, ItemListResponse } from '../shared/types'

export function getItems(filters: ItemFilter = {}, page = 1, pageSize = 20) {
  return apiRequest<ItemListResponse>('/items', {
    params: {
      page,
      page_size: pageSize,
      type: filters.type,
      search: filters.search,
      favorite: filters.favorite,
      needs_wash: filters.needs_wash,
      is_archived: filters.is_archived,
      sort_by: filters.sort_by,
      sort_order: filters.sort_order,
    },
  })
}

export function getItem(id: string) {
  return apiRequest<Item>(`/items/${id}`)
}

export function updateItem(id: string, data: Partial<Item>) {
  return apiRequest<Item>(`/items/${id}`, { method: 'PATCH', data })
}

export function uploadItem(filePath: string, formData: Record<string, string>) {
  return Taro.uploadFile({
    url: `${getApiBaseUrl()}/api/v1/items`,
    filePath,
    name: 'image',
    formData,
    header: getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {},
  }).then((res) => JSON.parse(res.data) as Item)
}
```

- [ ] **Step 2: Add outfit and user services**

Implement `getOutfits`, `suggestOutfit`, `acceptOutfit`, `rejectOutfit`, `getWeather`, `getPreferences`, `updatePreferences`, `getUserProfile`, and `syncWeChatMiniapp` using `apiRequest`.

- [ ] **Step 3: Typecheck**

Run: `cd miniapp && npm run typecheck`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add miniapp/src/services/items.ts miniapp/src/services/outfits.ts miniapp/src/services/user.ts
git commit -m "feat: add miniapp domain services"
```

---

## Task 9: Miniapp Home And Settings Pages

**Files:**
- Create: `miniapp/src/pages/home/index.tsx`
- Create: `miniapp/src/pages/home/index.scss`
- Create: `miniapp/src/pages/settings/index.tsx`
- Create: `miniapp/src/pages/settings/index.scss`

- [ ] **Step 1: Add home page with dashboard cards**

Build:

- greeting title
- weather card
- pending outfits card
- next scheduled card
- quick actions buttons
- insights list

Use `View`, `Text`, `Button`, and shared card styles. Pull data from miniapp services in `useEffect`.

- [ ] **Step 2: Add settings page**

Build:

- API base URL input for local/staging fallback
- access token display/clear control for debug mode
- WeChat sync button
- location fields
- temperature unit selector
- save button calling profile/preferences APIs

- [ ] **Step 3: Verify in Taro build**

Run: `cd miniapp && npm run build:weapp`

Expected: PASS and output under `miniapp/dist`.

- [ ] **Step 4: Commit**

```bash
git add miniapp/src/pages/home miniapp/src/pages/settings
git commit -m "feat: add miniapp home and settings pages"
```

---

## Task 10: Miniapp Wardrobe Flow

**Files:**
- Create: `miniapp/src/pages/wardrobe/index.tsx`
- Create: `miniapp/src/pages/wardrobe/index.scss`
- Create: `miniapp/src/pages/wardrobe/detail.tsx`
- Create: `miniapp/src/pages/wardrobe/detail.scss`
- Create: `miniapp/src/pages/wardrobe/add.tsx`
- Create: `miniapp/src/pages/wardrobe/add.scss`
- Create: `miniapp/src/components/ItemCard.tsx`
- Create: `miniapp/src/components/FilterSheet.tsx`

- [ ] **Step 1: Add wardrobe grid**

Implement two-column scroll grid with:

- search input
- sort selector
- filter toggles
- item cards with image, name/type, favorite badge, wash badge, processing overlay
- pull-to-refresh and load-more

- [ ] **Step 2: Add item detail page**

Implement:

- large image
- name/type/color metadata
- favorite toggle
- edit form
- mark washed
- log wear
- delete confirmation

- [ ] **Step 3: Add upload page**

Use `Taro.chooseMedia` and `uploadItem`.

Required flow:

1. Choose camera/gallery image.
2. Preview selected image.
3. Optional type/name/brand/color fields.
4. Submit with upload progress.
5. Navigate back to wardrobe and refresh.

- [ ] **Step 4: Verify build**

Run: `cd miniapp && npm run build:weapp`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add miniapp/src/pages/wardrobe miniapp/src/components/ItemCard.tsx miniapp/src/components/FilterSheet.tsx
git commit -m "feat: add miniapp wardrobe flow"
```

---

## Task 11: Miniapp Suggest And Outfit Flows

**Files:**
- Create: `miniapp/src/pages/suggest/index.tsx`
- Create: `miniapp/src/pages/suggest/index.scss`
- Create: `miniapp/src/pages/suggest/result.tsx`
- Create: `miniapp/src/pages/suggest/result.scss`
- Create: `miniapp/src/pages/outfits/index.tsx`
- Create: `miniapp/src/pages/outfits/index.scss`
- Create: `miniapp/src/components/OutfitCard.tsx`
- Create: `miniapp/src/components/OccasionChips.tsx`

- [ ] **Step 1: Add occasion chips component**

Use current Web occasion values: `casual`, `office`, `formal`, `date`, `sporty`, `outdoor`.

- [ ] **Step 2: Add suggest page**

Implement:

- weather card
- default occasion from preferences
- weather override controls
- generate button
- error/loading states

- [ ] **Step 3: Add result page**

Render:

- occasion badge
- weather summary
- reasoning/highlights
- item grid
- style note
- Try Another, Love It, reject icon

- [ ] **Step 4: Add outfits page**

Implement:

- search
- filter chips: All, My Looks, Worn, Pairings, Replacements, AI
- list cards
- light month selector/calendar summary

- [ ] **Step 5: Verify build**

Run: `cd miniapp && npm run build:weapp`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add miniapp/src/pages/suggest miniapp/src/pages/outfits miniapp/src/components/OutfitCard.tsx miniapp/src/components/OccasionChips.tsx
git commit -m "feat: add miniapp outfit flows"
```

---

## Task 12: CloudBase Deployment Artifacts

**Files:**
- Create: `cloudbase/api.Dockerfile`
- Create: `cloudbase/worker.Dockerfile`
- Create: `cloudbase/README.md`
- Modify: `README.md`

- [ ] **Step 1: Add API Dockerfile**

```dockerfile
# cloudbase/api.Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend /app

ENV PYTHONPATH=/app
ENV PORT=8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

- [ ] **Step 2: Add worker Dockerfile**

```dockerfile
# cloudbase/worker.Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend /app

ENV PYTHONPATH=/app

CMD ["arq", "app.workers.worker.WorkerSettings"]
```

- [ ] **Step 3: Document CloudBase unsupported boundaries**

In `cloudbase/README.md`, include:

- Docker Compose is not deployed to Cloud Hosting.
- PostgreSQL and Redis must be external managed services.
- local `/data/wardrobe` is not persistent in Cloud Hosting.
- worker service must not use scale-to-zero.
- CloudBase MySQL migration is out of scope.

- [ ] **Step 4: Commit**

```bash
git add cloudbase README.md
git commit -m "docs: add cloudbase deployment notes"
```

---

## Task 13: Final Verification

**Files:**
- No new files expected unless verification reveals required fixes.

- [ ] **Step 1: Backend tests**

Run: `cd backend && pytest -q`

Expected: PASS.

- [ ] **Step 2: Frontend Web tests remain stable**

Run: `cd frontend && npm test -- --run`

Expected: PASS.

- [ ] **Step 3: Miniapp build**

Run: `cd miniapp && npm run typecheck && npm run build:weapp`

Expected: PASS.

- [ ] **Step 4: Manual QA in WeChat Developer Tools**

Check:

- settings can sync or store token/API base.
- home loads weather and summaries.
- wardrobe grid loads and opens detail.
- upload creates a new processing item.
- suggest generates an outfit.
- outfit accept/reject actions update state.

- [ ] **Step 5: Commit verification fixes**

```bash
git add .
git commit -m "fix: complete miniapp cloudbase verification"
```

Only run this commit if verification required fixes.

---

## Self-Review

### Spec Coverage

- Taro miniapp shell: Tasks 6-8.
- Home, wardrobe, suggest, outfits, settings flows: Tasks 9-11.
- WeChat identity: Task 3.
- CloudBase storage adaptation: Tasks 1, 2, 5.
- Worker storage-key safety: Task 4.
- CloudBase deployment boundaries and docs: Task 12.
- Verification across backend, Web, miniapp: Task 13.

### Scope Control

The plan intentionally does not migrate PostgreSQL to CloudBase MySQL, rewrite the backend as Cloud Functions, replace the Web frontend, or implement payments/subscriptions. Those items are explicitly out of scope in the approved spec.

### Type Consistency

Backend remains centered on existing `UserSyncResponse`, `Item`, and `Outfit` API shapes. Miniapp services mirror existing Web hook operations while using Taro runtime APIs instead of browser APIs.
