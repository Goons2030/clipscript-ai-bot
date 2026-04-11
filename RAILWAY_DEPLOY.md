# Railway Deployment (Unified Monorepo)

This repository has backend code in `ClipScript AI/` and web UI in `ClipScript AI web/`.

## Recommended (works with Railpack auto-detection)

1. Deploy from GitHub on Railway.
2. Keep root directory as repository root.
3. Railway will detect Python using root `requirements.txt`.
4. Start command is defined via `Procfile` / `nixpacks.toml` and runs:
   - `python "ClipScript AI/app_unified.py"`

## Required environment variables

- `BOT_TOKEN`
- `DEEPGRAM_API_KEY`
- `WEBHOOK_URL=https://<your-railway-domain>/telegram/webhook`
- `TRANSCRIPTION_SERVICE=deepgram` (optional)

## Important

- App now binds to `PORT` automatically: `int(os.getenv("PORT", 5000))`.
- `GET /health` should return `status: ok`.
- `GET /` should serve web UI.

## Smoke test

```bash
curl https://<your-domain>/health
curl -X POST https://<your-domain>/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link":"https://vm.tiktok.com/abc123xyz"}'
```
