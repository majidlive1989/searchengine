# Deployment and operations

## Deployment boundary

This is a single-agency local pilot. One FastAPI process serves the frontend and API. SQLite is stored on local persistent storage. Run **one worker only**: source locks and background task ownership are in-process. The database has tenant-scoped repositories and tests, but there is no public multi-tenant signup or SaaS management layer.

Default network binding is loopback only. To expose it to an agency LAN, have your operator add a TLS reverse proxy, set `COOKIE_SECURE=true`, and set `ALLOWED_ORIGINS` to exact HTTPS origins. Do not use wildcard origins. Explicitly configure Docker port binding or `ATLAS_HOST` only after that network decision. Provider requests are external egress: Gemini when configured, the fixed execution bridge when configured. There is no vendor telemetry or automatic cloud sync.

## Identity and secrets

First startup requires an `ADMIN_PASSWORD` of at least 12 characters. `scripts/configure.py` generates a random one and writes `.env`, refusing to overwrite existing settings. Subsequent startup does not reset existing database passwords. Passwords use scrypt with random salts; session tokens are randomly generated and only their hashes are persisted. Cookies are HttpOnly, SameSite Strict, expire after eight hours, and are Secure when configured. Mutations require a custom header and known browser origin. Login throttling is process-local; production needs proxy-wide protections.

Admin creates users and sources; managers view/manage all cases in the agency; agents only manage their own cases. All staff can read source metadata. Source settings contain profile references and onboarding notes only; never enter passwords, cookies or API keys there. Gemini and native supplier API credentials can be saved in the app. They are Fernet-encrypted in the database with a local key at data/vault.key (or ATLAS_VAULT_KEY_FILE). The UI never reads secret values back. The host administrator can access this key, so use OS disk encryption and filesystem access controls. Optional bridge secrets remain environment-configured; browser sessions belong to that external execution service.

Account recovery by an authorized machine administrator (local installation): stop the app, activate the venv, set `PYTHONPATH=backend` (PowerShell: `$env:PYTHONPATH='backend'`), and run Python interactively:

```python
import getpass
from app import db
from app.security import password_hash
# Set the actual configured path if it is not data/copilot.db:
db.DB_PATH = 'data/copilot.db'
email = input('Account email: ').strip().lower()
password = getpass.getpass('New password (12+ characters): ')
assert len(password) >= 12
with db.connect() as c:
    row = c.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
    assert row, 'Account not found'
    c.execute('UPDATE users SET password=? WHERE id=?', (password_hash(password), row['id']))
    c.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
```

Record the recovery in your operational log. A production release should replace this maintenance procedure with an audited, controlled recovery flow and user deactivation.

## Backup and restore

Run from the project root. Example for a local installation:

```bash
python scripts/backup.py --database data/copilot.db --output backups/agency-2026-09-27.db
python scripts/restore.py --backup backups/agency-2026-09-27.db --output data/restored.db
```

Use a fresh filename each time. The backup uses SQLite's online backup API, runs an integrity check and creates a checksum sidecar. It is consistent even with WAL writes. When encrypted credentials exist, the backup also writes `.vault-key` and `.vault-key.sha256` sidecars. Restore needs all four files; it refuses a conflicting existing installation key. The backup set is **not encrypted by the script**; put it on encrypted, access-controlled storage. Backup files contain customer data and password hashes. Restore verifies the checksum and database integrity and clears sessions. It refuses to overwrite any existing target. Stop the app, edit `DATABASE_PATH=data/restored.db` in `.env`, then restart and validate record counts and sign-in. Keep the previous database until the restore check succeeds.

Docker backup, with a destination outside the active named volume:

```bash
docker compose exec atlas python scripts/backup.py --database /app/data/copilot.db --output /tmp/agency-backup.db
docker compose cp atlas:/tmp/agency-backup.db ./agency-backup.db
docker compose cp atlas:/tmp/agency-backup.db.sha256 ./agency-backup.db.sha256
# If the installation has saved credentials, also copy:
docker compose cp atlas:/tmp/agency-backup.db.vault-key ./agency-backup.db.vault-key
docker compose cp atlas:/tmp/agency-backup.db.vault-key.sha256 ./agency-backup.db.vault-key.sha256
```

Schedule backups via the host's Task Scheduler or cron after choosing retention/encryption policy. No schedule is installed automatically. Test restore to a separate installation before relying on backups. Never copy only a live `.db` file with file-copy tools while WAL changes are pending.

## Failures and restart

Each search has source-level jobs and timestamps. A failure leaves healthy sources visible. Malformed/mismatched responses are rejected rather than patched with guesses. Login/OTP/CAPTCHA handling belongs to the execution service and requires a human. An edited request invalidates the old run; late results cannot become current or enter offers. Rates from old runs and inactive sources cannot be newly approved.

If the API process stops mid-search, startup marks the interrupted run failed, marks incomplete jobs `WORKER_RESTARTED`, and returns the case to `READY_TO_SEARCH`. A staff member must review and retry. Completed data remains. The pilot has no automatic retries, distributed locks or durable queue.

## Limits to plan around

- Responses are persisted as JSON aggregates. Very long case histories, many users, and large datasets require pagination and normalized storage work before scale.
- A job's execution timeout applies after acquiring the per-source lock. Queued time is not bounded in this release. The job includes a deadline which a real bridge must enforce.
- Rate validity does not reserve inventory. Approved printouts retain their captured/expiry timestamps and remain subject to revalidation. Re-search before a live commercial commitment.
- Metrics include demo runs and do not prove supplier performance or time savings.
- The app has no automated email, WhatsApp, booking, cancellation or payment.
- Frontend modals include labelled native form controls; full focus-trap and screen-reader audits remain for production accessibility QA.
- Dependency pins are provided; perform your organization's vulnerability scan and update validation before deployment. No security certification is claimed.
- FastAPI's default interactive docs use CDN resources. `/openapi.json` is available offline. Do not expose internal API documentation publicly without appropriate access policy.

## Update discipline

Back up first. Stop the app, replace code/build artifacts, install pinned dependencies, run tests and restart. Keep `.env` and `data` separate from replacement code. Versions 0.1 and 0.2 use the same aggregate schema version 1; it is not a general migration/rollback framework. Do not run future incompatible schemas against a production database without an explicit migration and restore plan.
