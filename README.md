# Atlas Travel Agency Copilot 0.2.1

Install the application first, then add your suppliers and AI settings yourself inside the app. You do not need to provide supplier details to the developer before running it.

A full-stack local application: React/TypeScript frontend, FastAPI backend, SQLite persistence, staff roles, cases, supplier configuration, multi-source search, manually verified rates, offer markup, approval, audit history and print/PDF output. The frontend is already compiled in this package.

## Windows installation

Install Python 3.12. Extract the ZIP and open PowerShell inside `travel-copilot`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe scripts\configure.py
.\.venv\Scripts\python.exe scripts\run.py
```

Open **http://localhost:8000**. Sign in as **admin@agency.local** with the random password printed by `configure.py`. Save that password privately. No default password is supplied. Node.js is not needed unless you edit/rebuild the frontend.

For later starts:

```powershell
.\.venv\Scripts\python.exe scripts\run.py
```

## Upgrade an existing 0.1 installation

1. Stop Atlas and back up the existing database.
2. Extract 0.2 into a separate folder.
3. Copy your existing `.env` and entire `data` folder into the new folder. Preserve any custom `DATABASE_PATH`. Never replace your data with sample data.
4. Create/install the new virtual environment using the first two installation commands above.
5. Run `scripts\run.py`. **Do not run configure.py again.** Existing users, passwords, sources, cases and offers remain in the database. This release adds new record types without dropping or rebuilding the old schema.
6. After you save credentials in 0.2, keep `data/vault.key` together with the database for recovery; backups now include the key sidecar.

## Add your suppliers after running

Go to **Source Studio → Add source**, enter a name, choose Flight or Hotel, and choose a connection type. The configuration panel opens immediately after creation.

| Connection type | What you enter | What Atlas does |
|---|---|---|
| Direct JSON API | Authorized HTTPS search endpoint, token/key, request template, response field mapping | Calls the supplier directly and validates each returned rate; no separate bridge needed |
| Supplier website / manual rates | Supplier website URL and authorization confirmation | Opens the site in your browser; staff enter newly verified rates for a confirmed case and then price/approve an offer |
| Custom execution bridge | Profile reference and separately deployed adapter | Supports custom or browser-driven workflows implemented outside Atlas |
| Demonstration | No supplier account | Runs visibly labelled synthetic fixtures for evaluation only |

**A website URL alone does not create reliable automatic search.** For automatic operation, the supplier needs a compatible authorized JSON API, configured request/response fields, or a custom tested adapter. Website-only sources work through explicit manual rate entry. No universal browser teaching, CAPTCHA bypass, or unverified OpenClaw runtime is claimed.

### Direct API setup

1. Create a Direct JSON API source. Use its supplier API documentation to fill in the endpoint, authentication, request template, result-array path and field map.
2. Save the credential in its dedicated password field. Never put a credential in the URL, notes or request template. It is encrypted locally and not returned to the UI.
3. Match canonical fields to supplier JSON paths, e.g. `net_price` → `pricing.total`. This must be the total for the entire confirmed party/trip/stay, including taxes. Per-person/nightly amounts require a custom adapter; do not relabel them as totals.
4. If you bind identity fields to the confirmed request, explicitly verify that the API scopes every response row to those dates, travelers and route. Otherwise map them from the response.
5. Confirm the endpoint is authorized and search-only. Save creates an immutable draft version and disables the old activation until retested.
6. Run three distinct successful golden searches, manually compare results with the supplier, then click **Approve & activate**. Changing route, passenger count or dates makes tests distinct.

The built-in connector supports GET query parameters or POST JSON, Bearer/custom-header authentication, dot-separated JSON paths, up to 100 results / 1 MB, public HTTPS endpoints on port 443, no redirects and a bounded timeout. Private network APIs, OAuth flows, SOAP/XML, custom signatures, pagination beyond 100 records and per-unit price conversion require an adapter. Native connections bypass environment proxies to enforce the public-IP policy.

### Website-only supplier setup

1. Create a Supplier website source, save its HTTPS URL and confirm agency authorization.
2. Create/open a request and confirm the travel details.
3. Choose **Enter supplier rates**, select the supplier and open its website. Log in yourself in your own browser.
4. Enter the exact current total, supplier reference, itinerary/room details, cancellation conditions and validity. Verify every requested service and check the review confirmation.
5. Save; the rates are marked **manually verified** and carry the entering staff member in the audit record. Select the rates and draft/approve the offer normally.

Manual capture replaces the current result set, retains old history, and cannot mix with an earlier search or demo rate. It never fabricates a supplier price.

## Configure AI after running

Open **Settings → Configure AI after installation**. Enter your Gemini model ID and API key, enable it, save, and test the saved connection. Changes apply immediately without a restart. Leave the key blank to retain it or select Remove to clear it. Saved in-app settings take precedence over environment defaults.

Without Gemini, Atlas runs with its bounded English/Persian offline parser and the structured form. Uploaded audio is sent to Gemini only when enabled, not retained by this app, and its transcript must be reviewed before extraction. Dates must be reviewed; offline parsing requires Gregorian `YYYY-MM-DD` dates and does not resolve Persian-calendar or relative dates. Searches currently support adults only and the included airport list.

## First walkthrough without live suppliers

Source Studio → Load demo sources → New request → enter a customer → review/confirm travel details → search → select flight/hotel → add markup → create draft → approve → print/save PDF. Demo rates and printouts remain marked not bookable. The app never automatically books, pays, cancels or sends a message.

## Linux / macOS

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python scripts/configure.py
.venv/bin/python scripts/run.py
```

## Docker

```bash
python scripts/configure.py
docker compose up --build -d
docker compose logs --tail=50 atlas
```

The named volume persists both database and vault key. On Windows use `py -3.12` for configuration if needed. Open http://localhost:8000. Never use `docker compose down -v` unless you intend to delete all installation data. Docker configuration is supplied but was not built in the development environment.

## Development and verification

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm run build
```

For frontend development, run the backend and `npm run dev` in `frontend` in another terminal; visit http://localhost:5173. Frontend changes require rebuilding before using the compiled same-origin UI. Use one API worker; this local release does not implement a distributed durable job queue.

API schema: http://localhost:8000/openapi.json . Mutations require `X-Requested-With: Atlas`; case creation, search, manual rate capture and offer creation also require an `Idempotency-Key` header. Browser sessions are HttpOnly and role-scoped.

## Included documentation

- `docs/MANUAL_SETUP.md`: connection examples and setup reference
- `docs/OPERATIONS.md`: deployment, backups and recovery
- `docs/IMPLEMENTATION.md`: delivered scope and remaining production boundaries
- `docs/EXECUTION_CONTRACT.md`: optional custom execution adapter contract
- `docs/TEST_REPORT.md`: verification results and unverified areas
- `docs/QUICKSTART_FA.md`: Persian setup guide

Supplier compatibility, real rate accuracy and Gemini account access must still be validated using your accounts after configuration. This release is a usable local application with manual onboarding; it is not a claim that every production feature in the full blueprint is complete.
