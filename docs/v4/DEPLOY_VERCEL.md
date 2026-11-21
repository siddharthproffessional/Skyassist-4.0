# Deploying SkyAssist 4.0 on Vercel

The `vercel` branch is a generated, slim bundle (`python3 scripts/build_vercel_bundle.py`): the FastAPI app
(`api.server:app`) runs as a Vercel Function, and `public/` (the exported 3D frontend) is served by the CDN.

Project environment variables: `SKYASSIST_DB=/tmp/skyassist.sqlite`, `SKYASSIST_SSE=off`,
`SKYASSIST_SESSION_SECRET=<random>`; optional `GEMINI_API_KEY`, `GROQ_API_KEY`.

**Serverless trade-offs (read before a live demo):**
* The SQLite database lives in the function instance's `/tmp`. It is rebuilt from the synthetic seed on every cold
  start, so scenario results reset after idle periods, and two concurrent instances can briefly show different
  state. Click **Reset synthetic dataset** in `/recovery` (or **Start** in `/demo`) before presenting.
* Sessions are signed cookies (HMAC-SHA256), so a sign-in survives instance changes; sign-out only clears the cookie.
* Live server-sent events are off; the browser polls every 6 s and refreshes immediately after its own actions.
* For durable state, run the single-process server (`uvicorn api.server:app`) on a VM or container instead.
