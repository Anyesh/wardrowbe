# Outfit try-on

Outfit try-on shows an outfit on a reference photo of you. It is opt-in: with nothing configured the
feature does not exist, the web app hides every try-on control, and the try-on endpoints answer
`503 TRY_ON_DISABLED`.

## What users see

- **Settings > Try-on photo**: upload one full-length photo, facing the camera, in fitted clothes and
  even light. It can be replaced or removed; doing either deletes the try-on images already drawn
  from it.
- **Outfit page** and the **Suggest** page (single-outfit view): a **See it on me** button draws one
  front image of you wearing that outfit's items. The image can be regenerated or deleted. The image
  is reused until the outfit's items or your photo change; then it is marked as out of date.

## Enabling it

Set the first three variables on the backend (`docker-compose.yml` passes them to the API and the workers):

| Variable | Description |
|----------|-------------|
| `AI_IMAGE_BASE_URL` | Base URL of an OpenAI-compatible API; `/chat/completions` is appended |
| `AI_IMAGE_API_KEY` | API key for that provider |
| `AI_IMAGE_MODEL` | Image-generation model name |
| `AI_IMAGE_DAILY_LIMIT` | Optional. Generations per user per day (default 20) |
| `AI_IMAGE_TIMEOUT` | Optional. Seconds to wait for one image (default 180); the job's own deadline is this plus 60 |

These are separate from the `AI_*` settings used for tagging and suggestions, so you can use a
different provider for each.

Example with [OpenRouter](https://openrouter.ai):

```env
AI_IMAGE_BASE_URL=https://openrouter.ai/api/v1
AI_IMAGE_API_KEY=sk-or-your-key-here
AI_IMAGE_MODEL=google/gemini-nano-banana-2.1
```

The request uses OpenRouter's image-generation format (`modalities: ["image", "text"]`, images read
from `choices[0].message.images`). A provider that does not return images that way will not work.

## Workers

Try-on jobs run on the **image worker** (queue `arq:images`), not the tagging worker, so a slow
provider call never holds up item tagging. They share that worker with rotation and background
removal; with the default `IMAGE_WORKER_CONCURRENCY=1` those wait behind a running try-on, so
consider setting it to 2. A job runs once (no automatic retry, since every call is paid); if one is
lost, the outfit page offers **Retry** after 15 minutes.

When a regeneration fails, the previous image is kept and shown with a note.

## Cost

Every generation is a paid call and is never retried automatically (neither by the job queue nor by the app). At the time of writing the model
above costs roughly US$0.03 per image; check your provider's pricing. `AI_IMAGE_DAILY_LIMIT` caps
spending per user (regenerating counts), and requests are also limited to 5 per minute per user.

## Privacy

Your reference photo is stored on your own server, but **on each generation it is sent to the
configured image provider**, together with photos of the outfit's items. Choose a provider you trust
with that, or do not enable the feature. The photo and generated images are only visible to the
account that owns them, including within a family, and are deleted when you remove or replace the
photo or delete the try-on or the outfit.
