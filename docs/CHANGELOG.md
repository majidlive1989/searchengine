# 0.2.1

- Add request_id and run_id expression indexes, including created DESC ordering.
- Filter case runs/results/offers and search-run results in SQL rather than decoding every object of that kind in the tenant.
- Apply indexes at startup without rewriting or deleting stored entities.
- Add migration, isolation, ordering and query-plan regression tests.

Remaining limits: the aggregate objects schema and dashboard-wide scans remain; this is not normalization or pagination. Main orchestration still resides in main.py. Native source TTL is configurable from 1 to 15 minutes but the global 15-minute cap remains. Persian/relative dates require manual verification and Gregorian input. Search updates use polling; SSE is not implemented. A prompt instruction alone does not establish prompt-injection safety; model output remains subject to typed validation and explicit human confirmation. Browser content is not fed into the current Gemini extraction path.

Upgrade: stop the app; back up the existing folder; extract this release separately; copy .env and the entire data folder (including vault.key) to the new folder. Preserve any custom DATABASE_PATH. Install dependencies in a new virtual environment and run scripts/run.py. Do not rerun configure.py. Indexes are created automatically on startup; allow time for index creation with larger databases.
