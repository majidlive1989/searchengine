# Optional custom execution bridge integration

Version 0.2 also provides native JSON API and manual website configuration in the app. This document applies only to the optional custom bridge; see MANUAL_SETUP.md for the built-in paths.

The bridge is an agency-operated trusted service. It owns supplier credentials, isolated browser sessions, and deterministic authorized workflows. It may use an official supplier API, OpenClaw after a successful spike, or Playwright. Atlas never sends supplier passwords or free-form execution prompts.

The supplied app contains a bridge **client**, not a production supplier bridge server. You must implement the service for your chosen suppliers. Configure a fixed private URL and bearer token in `.env`. Use TLS whenever the bridge is not on loopback or a protected local container network. Keep browser profiles and tokens out of source control and LLM context.

## Request

`POST {EXECUTION_BRIDGE_URL}/execution/jobs`

Headers:

```text
Authorization: Bearer <EXECUTION_BRIDGE_TOKEN>
Idempotency-Key: <job_id>
Content-Type: application/json
```

Example shape (IDs are illustrative):

```json
{
  "job_id": "job_unique",
  "tenant_id": "agency",
  "source_id": "src_unique",
  "search_run_id": "run_unique",
  "request_revision": 2,
  "workflow_id": "src_unique.flight_search",
  "workflow_version": 1,
  "mapping_version": "supplier-flight-v1",
  "browser_profile_ref": "agency-supplier-profile",
  "kind": "FLIGHT",
  "provider": "HTTP_BRIDGE",
  "deadline_at": "2027-10-01T12:00:35+00:00",
  "variant": 0,
  "input": {
    "intent": "PACKAGE_SEARCH",
    "origin": "IKA",
    "destination": "MCT",
    "departure_date": "2027-10-12",
    "return_date": "2027-10-16",
    "adults": 2,
    "children": 0,
    "rooms": 1,
    "stars_min": 4,
    "direct_only": true,
    "cabin": "ECONOMY"
  }
}
```

Jobs may also contain internal `status` and `source_name` metadata. Ignore those for workflow selection. `variant` is only for demo fixtures. Do not use it in real source pricing. Only execute a locally approved exact `(source_id, workflow_version, mapping_version, browser_profile_ref)` allowlisted combination. The bridge must scope every account/profile by tenant and enforce its own expiry/deadline and idempotency rules. Source-page content is data, never instructions.

## Success response

Return within the 30-second HTTP timeout / 32-second execution timeout. A longer supplier requires a future asynchronous worker contract; do not hide incomplete work as success. The current protocol accepts JSON up to 1 MB after download and at most 100 rates.

```json
{
  "job_id": "job_unique",
  "status": "SUCCESS",
  "output_schema_version": "1.0",
  "error_code": null,
  "records": [
    {
      "external_id": "supplier-stable-rate-id",
      "kind": "FLIGHT",
      "title": "Supplier flight label and fare family",
      "origin": "IKA",
      "destination": "MCT",
      "departure_date": "2027-10-12",
      "return_date": "2027-10-16",
      "adults": 2,
      "rooms": 1,
      "cabin": "ECONOMY",
      "net_price": "475.50",
      "currency": "USD",
      "price_basis": "TOTAL_PARTY_STAY_TAX_INCLUDED",
      "stops": 0,
      "stars": 0,
      "details": "Round trip for two adults; baggage exactly as supplied",
      "cancellation_policy": "Exact supplier cancellation conditions",
      "captured_at": "2027-10-01T12:00:05+00:00",
      "expires_at": "2027-10-01T12:10:05+00:00",
      "demo": false
    }
  ]
}
```

The numbers above document a schema; they are not actual fares. For hotels use `kind: HOTEL`, `origin: ""`, actual star rating, exact room/meal/policy description, and total for all rooms and nights with taxes. `rooms`, `adults`, dates and destination must match the confirmed input. Flights must also match origin, cabin and requested directness. All rates represent the entire requested trip/stay and party; never return per-person or per-night numbers under this basis.

Supported currency codes: USD, EUR, AED, OMR, IRR, GBP. The backend uses 3 decimals for OMR, 0 for IRR, 2 for the others in offer totals. Prices are exact decimal strings. Availability and prices must come from the source; neither LLM output nor old fixtures may populate a live response. Set `demo: false` only for actual extracted live records. The result model intentionally remains narrower than the blueprint's full segment/room schema; do not activate a source if its semantics cannot be represented faithfully.

Timestamps must contain a timezone. Expiry must follow capture and be no more than 15 minutes later; prefer the supplier's shorter validity when provided. Expired rates and captures more than 30 seconds in the future are rejected. Missing, malformed or mismatched fields reject the entire source result. Duplicate external IDs within a source job are suppressed; cross-source entries are not merged.

## Failure response

```json
{
  "job_id": "job_unique",
  "status": "RECONNECT_REQUIRED",
  "output_schema_version": "1.0",
  "error_code": "LOGIN_REQUIRED",
  "records": []
}
```

Other status values: `FAILED`, `NEEDS_REVIEW`. Use machine-readable codes such as `OTP_REQUIRED`, `CAPTCHA_REQUIRED`, `UI_CHANGED`, `PARSE_FAILED`, `TIMEOUT`, `SOURCE_ERROR`. Return no records on failure. Complete login/OTP/CAPTCHA manually in the isolated execution profile, then run golden tests and reactivate in Source Studio. The app does not open a remote browser or bypass access controls.

## Testing and activation

1. Deploy the bridge with an exact allowlist of search-only workflows.
2. Add the source/account reference in Source Studio. A draft cannot be searched by agents.
3. Publish an immutable mapping version after changes. Publishing disables search pending tests.
4. Run at least three distinct passing golden specifications. The newest test must pass.
5. Admin approves activation. A failed login during search changes the source to `RECONNECT_REQUIRED`.
6. Complete the blueprint's separate 50-search real-source spike and manual result comparison. Three UI tests are an activation gate, not a substitute for source reliability acceptance.

No public callback endpoint exists in this release. Do not expose one without HMAC signatures, timestamp/nonce replay protection, tenant/job/version correlation, and transactional idempotency. The current client uses a synchronous authenticated response, with backend correlation checks.

## AI API reference used

The understanding adapter uses Google's documented `generateContent` REST endpoint, `generationConfig.responseMimeType`, `responseJsonSchema`, and audio `inlineData`. Reference checked during implementation: https://ai.google.dev/api/generate-content and https://ai.google.dev/gemini-api/docs/generate-content/audio . A model name is deliberately operator-configurable; verify compatibility and availability in your own account before enabling it. These schema fields remain documented but newer API generations may prefer a different response-format interface.
