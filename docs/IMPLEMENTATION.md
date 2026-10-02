# Delivered scope in version 0.2

This upgrade completes post-installation supplier and AI configuration. You can install an empty workspace and enter the connections yourself later. Real supplier compatibility still depends on its documented interface and your account access.

| Area | Delivered | Boundary |
|---|---|---|
| Application | React/TypeScript UI, FastAPI backend, persistent SQLite | Local single-agency deployment, one API worker |
| Staff | Login, admin/manager/agent roles, agent case ownership, tenant-scoped records | No SSO/MFA/invitations or user lifecycle UI |
| AI setup | In-app Gemini key/model/enable settings, saved-connection test, immediate effect | Live provider access requires your key; model/voice quality not verified against a real account |
| Credentials | Fernet-encrypted secret records, no key readback, local key file, key-aware backups | Not an external HSM/enterprise vault; host admin can access the local installation |
| Native supplier API | In-app endpoint, GET/POST, Bearer/custom header, request templates, field maps, result validation | Public HTTPS JSON search APIs with supported pricing/schema; no OAuth/SOAP/custom signing/automatic pagination |
| Source lifecycle | Draft immutable versions, 3 distinct golden tests, admin activation, disable/reconnect | No self-teaching website automation or universal source compatibility |
| Website suppliers | Manual website registration, user opens supplier portal, verified rate-entry form, actor/time audit | Search and login are manual; no browser automation claimed |
| Custom integrations | Optional typed HTTP execution bridge client | Custom supplier/OpenClaw/Playwright service not included |
| Requests | Persistent cases, English/Persian extraction, confirmation, edits, history, status tracking | Adults only; bounded airport list; Gregorian date confirmation |
| Search | Independent concurrent jobs, per-source locks, timeout, partial results, stale-job suppression | In-process jobs; no durable distributed queue, automatic retry/circuit breaker |
| Rates | Source/version trace, exact Decimal values, expiration, current-run enforcement, manual provenance | No cross-source hotel matching, complex fare/room equivalence, per-unit conversion or FX |
| Offers | Flight/hotel selection, markup, approval, customer print/PDF | No automatic booking/payment/cancellation/messaging; PDF browser layout not visually verified |
| Analytics | Stored request/run/offer metrics and case audit history | Demo/manual runs are included; not a validated live supplier SLO or measured time-to-quote gain |
| Deployment | Windows/Linux commands, prebuilt UI, Docker definition, backup/restore | Docker engine and browser UI verification unavailable in the development environment |

## Verification and live acceptance

Automated tests exercise native API execution with a mocked supplier response, configuration lifecycle, encryption/redaction, public-IP restrictions, request pinning/TLS hostname, redirect/auth failure handling, manual supplier-to-offer workflow, backup restoration of encrypted keys and prior core behavior. No real supplier or Gemini credentials were supplied, so tests do not establish real-world supplier accuracy or availability.

Before live agency use, configure each source, manually compare fields against its own portal, honor its authorization and pricing semantics, and test login expiry, empty results and failure responses. Three configuration tests are not a replacement for the blueprint's 50-search source reliability spike.

Remaining full-blueprint work includes browser workflow teaching/repair, real-source certification, child/infant/room occupancy modelling, distributed queues, normalized production migrations, complete Persian localization and Jalali entry, stronger identity lifecycle, vendor licensing/control plane, signed updates, production hardening and operational SLAs. None is silently represented as finished in this release.
