# Configure suppliers inside the running app

All examples below are configuration examples, not real supplier credentials or prices. Use your supplier's authorized API documentation. You can do all setup after installation.

## Example request mapping

If a supplier accepts `from`, `to`, `depart`, `return`, and `passengers`, configure:

```json
{
  "from": "{{origin}}",
  "to": "{{destination}}",
  "depart": "{{departure_date}}",
  "return": "{{return_date}}",
  "passengers": "{{adults}}"
}
```

Placeholders must occupy the whole JSON value, preserving numbers and booleans. Available values: intent, origin, destination, departure_date, return_date, adults, children, rooms, stars_min, direct_only, cabin. Do not use free-form expressions, code, or secrets in this template.

## Example response mapping

Suppose the authorized API returns:

```json
{
  "data": {
    "offers": [
      {
        "id": "supplier-rate-reference",
        "name": "Flight and fare label",
        "pricing": {"total": "475.50", "currency": "USD"},
        "stops": 0,
        "description": "Exact itinerary and baggage",
        "rules": {"cancellation": "Exact supplier cancellation conditions"}
      }
    ]
  }
}
```

Set result-array path to `data.offers` and mapping to:

```json
{
  "external_id": "id",
  "title": "name",
  "net_price": "pricing.total",
  "currency": "pricing.currency",
  "stops": "stops",
  "details": "description",
  "cancellation_policy": "rules.cancellation"
}
```

For a flight source, static metadata can be:

```json
{"price_basis":"TOTAL_PARTY_STAY_TAX_INCLUDED","stars":0}
```

For a hotel source, map `stars` from its result and use static `stops: 0` instead. Never make up a price, identity, description, cancellation policy or availability. A supplier reference, title, total, details and policy must come from response fields. Missing data rejects the source result.

If the API contract guarantees every row is for the requested party, route and dates, the configuration can explicitly bind `origin,destination,departure_date,return_date,adults,rooms,cabin` to those confirmed inputs. This is an admin assertion requiring manual comparison, not automatic semantic proof. If that guarantee is absent, remove those names from the bound field list and map each from the supplier response. Hotel origin is normalized to empty.

Prices must already include the whole round trip when applicable, the whole party, all rooms/nights and taxes. No silent arithmetic/FX conversions occur in the connector. Currency support is USD, EUR, AED, OMR, IRR, GBP. Choose a validity window no longer than your supplier allows and no more than 15 minutes. Captured time is the local fetch time, not proof of reserved inventory.

## Credentials and destinations

Keys are saved in an encrypted local secret record. UI reads return only whether a key exists. Updating a credential publishes a fresh draft configuration and requires retesting. Changing the endpoint requires re-entering its credential so an existing key is not silently forwarded elsewhere. Use public HTTPS URLs with port 443; credentials, fragments and query strings are forbidden in endpoint URLs. Put query parameters in the request template. DNS results are checked for public addresses and the chosen IP is pinned with the original TLS hostname. Redirects and environment proxies are disabled.

Only configure search endpoints. The permission checkbox is your explicit attestation of supplier authorization and read-only semantics; it cannot technically prove that a third-party POST endpoint has no side effects. No arbitrary supplier URL is auto-detected or learned.

## Website/manual mode

Save the supplier's HTTPS website URL and authorization confirmation. No API mapping is required. Agents open the supplier themselves, authenticate there, and enter verified prices and terms into their case. Atlas records who entered the rate and the time/validity. This mode does not automate searching the external website or store its login session.

## Troubleshooting

| Message | Action |
|---|---|
| PUBLIC_HTTPS_URL_REQUIRED | Use a public HTTPS endpoint on 443, with no URL credentials/query/fragment |
| CREDENTIAL_REQUIRED | Save the supplier token in its dedicated credential field |
| LOGIN_REQUIRED | Renew the supplier token, save configuration and rerun tests |
| REDIRECT_NOT_ALLOWED | Use the authorized API's final endpoint directly |
| EXECUTION_OR_SCHEMA_FAILED | Check JSON paths, date/price types, required fields and exact request semantics |
| RESULTS_MUST_BE_ARRAY_MAX_100 | Set the correct array path or implement a source-specific pagination adapter |
| UNKNOWN_TEMPLATE_FIELD | Use one of the documented confirmed-input field names |
| Three golden searches required | Change route, dates or traveler count and pass distinct tests for the current version |

Existing OpenClaw/Playwright or custom API integrations can still use the optional HTTP bridge contract. They are not needed for supported direct JSON APIs or manual suppliers.
