# Verification report

Release 0.2.1 · Linux / Python 3.12 / Node 24 build environment.

## Completed checks

- Backend suite: **45 passed**. One dependency deprecation warning concerns FastAPI/Starlette TestClient's current `httpx` integration; no test failed.
- Frontend: TypeScript check and Vite production build passed.
- Python source compilation passed.
- SQLite backup/restore round trip passed, including checksum validation, preserved records, refusal to overwrite an existing target, and revoked restored sessions.

The test suite exercises request creation, explicit confirmation, concurrent demo sources, offer arithmetic, approval/audit persistence, idempotency and payload conflicts, authentication/CSRF, role and tenant boundaries, old/expired/duplicate/mixed-currency rate rejection, incomplete input, Persian-digit parsing, source activation/version gates, source failure isolation, malformed response rejection, stale job suppression after modification, restart recovery, disabled sources, operator demo disable, and missing bridge/voice configuration.

Additional configuration tests cover encrypted credential storage/redaction, admin-only settings, API version activation, typed request templates, response mapping, public-IP and pinned-TLS transport, HTTP error handling, manual rates and idempotency, and credential backup/restore. Supplier and Gemini requests are mocked; no live connection was verified.

## Browser visual verification

Attempted a Chromium end-to-end run, but the environment blocked the browser process at startup (`socket() failed: Operation not permitted`). No browser interaction or screenshot checks completed. Visual layout, mobile overflow, keyboard navigation, and print layout therefore remain unverified. The TypeScript/production build passed; this is not a substitute for browser QA.

## Integration boundaries

No live supplier credentials or Gemini API key were provided, so external provider functionality and actual price/availability accuracy have not been verified. The bridge is a client contract requiring a source-specific external implementation. Docker engine was not available; Dockerfile and Compose are supplied but an image build was not exercised. No production load, penetration, recovery-time objective, or supplier reliability certification is claimed.

## Reproduce backend checks

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
```

Tests use isolated temporary databases and mocked/fake source behavior; they do not touch an agency database or call live suppliers.

## Reproduce frontend build

```bash
cd frontend
npm ci
npm run build
```

## 0.2.1 relationship-query regression

Tests exercise upgrades of an existing populated database, repeated initialization, tenant/kind/parent isolation, newest-first ordering, missing matches, and SQLite EXPLAIN QUERY PLAN selecting the relationship index without a temporary sort. No production performance benchmark was run.
