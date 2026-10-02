import React, { useEffect, useState } from "react";
import {
  Check,
  KeyRound,
  Save,
  Play,
  ArrowUpRight,
  Plus,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Upload,
} from "lucide-react";
type Obj = Record<string, any>;
type API = (path: string, method?: string, body?: any) => Promise<any>;
function Notice({ error, success }: { error: string; success: string }) {
  return (
    <>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      {success && (
        <div role="status" className="info-banner">
          {success}
        </div>
      )}
    </>
  );
}

export function AISettingsPanel({
  api,
  onChange,
}: {
  api: API;
  onChange: () => Promise<void>;
}) {
  const [cfg, setCfg] = useState({ enabled: false, model: "", has_key: false }),
    [key, setKey] = useState(""),
    [clear, setClear] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  useEffect(() => {
    api("/settings/ai")
      .then(setCfg)
      .catch((e) => setError(e.message));
  }, []);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card setting-card">
      <h2>
        <KeyRound size={20} /> Configure AI after installation
      </h2>
      <p>
        Save your Gemini key and model here. Changes take effect immediately; no
        restart or .env edit is required.
      </p>
      <Notice error={error} success={success} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            setCfg(
              await api("/settings/ai", "PUT", {
                enabled: cfg.enabled,
                model: cfg.model,
                api_key: key || null,
                clear_key: clear,
              }),
            );
            setKey("");
            setClear(false);
            await onChange();
            setSuccess(
              "Settings saved. Your key is encrypted locally and is never sent back to the interface.",
            );
          });
        }}
      >
        <label>
          Gemini model ID
          <input
            value={cfg.model}
            placeholder="Enter a model enabled for your account"
            pattern="[a-zA-Z0-9_.-]*"
            onChange={(e) => setCfg({ ...cfg, model: e.target.value })}
          />
        </label>
        <label>
          API key
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            placeholder={
              cfg.has_key
                ? "Key saved — leave blank to keep it"
                : "Paste your API key"
            }
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={clear}
            onChange={(e) => setClear(e.target.checked)}
          />
          Remove the saved key
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={cfg.enabled}
            onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })}
          />
          Enable Gemini text and voice (requests leave this machine)
        </label>
        <div className="panel-actions">
          <button className="primary" disabled={busy}>
            <Save size={15} />
            Save AI settings
          </button>
          <button
            type="button"
            className="secondary"
            disabled={busy || !cfg.has_key}
            onClick={() =>
              run(async () => {
                const r = await api("/settings/ai/test", "POST");
                setSuccess(r.message);
              })
            }
          >
            <Play size={15} />
            Test saved connection
          </button>
        </div>
      </form>
    </section>
  );
}

function defaults(kind: string) {
  return {
    endpoint: "",
    method: "POST",
    auth_type: "BEARER",
    auth_header: "X-API-Key",
    request_template: {
      origin: "{{origin}}",
      destination: "{{destination}}",
      departure_date: "{{departure_date}}",
      return_date: "{{return_date}}",
      adults: "{{adults}}",
      rooms: "{{rooms}}",
      cabin: "{{cabin}}",
    },
    records_path: "results",
    field_map: {
      external_id: "id",
      title: "name",
      net_price: "price",
      currency: "currency",
      details: "details",
      cancellation_policy: "cancellation_policy",
      ...(kind === "FLIGHT" ? { stops: "stops" } : { stars: "stars" }),
    },
    static_fields: {
      price_basis: "TOTAL_PARTY_STAY_TAX_INCLUDED",
      ...(kind === "FLIGHT" ? { stars: 0 } : { stops: 0 }),
    },
    context_fields: [
      "origin",
      "destination",
      "departure_date",
      "return_date",
      "adults",
      "rooms",
      "cabin",
    ],
    ttl_minutes: 5,
    authorized_search_only: false,
    scope_confirmed: false,
  };
}

export function SourceConfigPanel({
  source,
  api,
  onChange,
}: {
  source: Obj;
  api: API;
  onChange: (s: Obj) => Promise<void>;
}) {
  const [cfg, setCfg] = useState<Obj>(defaults(source.kind)),
    [credential, setCredential] = useState(""),
    [hasCredential, setHasCredential] = useState(false),
    [clear, setClear] = useState(false),
    [request, setRequest] = useState(
      JSON.stringify(defaults(source.kind).request_template, null, 2),
    ),
    [mapping, setMapping] = useState(
      JSON.stringify(defaults(source.kind).field_map, null, 2),
    ),
    [statics, setStatics] = useState(
      JSON.stringify(defaults(source.kind).static_fields, null, 2),
    ),
    [contexts, setContexts] = useState(
      defaults(source.kind).context_fields.join(","),
    ),
    [website, setWebsite] = useState(source.website_url || ""),
    [authorized, setAuthorized] = useState(false),
    [notes, setNotes] = useState(source.notes || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  useEffect(() => {
    if (source.provider === "JSON_API")
      api("/sources/" + source.id + "/api-config")
        .then((r) => {
          setHasCredential(r.has_credential);
          if (r.config) {
            setCfg(r.config);
            setRequest(JSON.stringify(r.config.request_template, null, 2));
            setMapping(JSON.stringify(r.config.field_map, null, 2));
            setStatics(JSON.stringify(r.config.static_fields, null, 2));
            setContexts(r.config.context_fields.join(","));
          }
        })
        .catch((e) => setError(e.message));
  }, [source.id]);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function refreshed() {
    const ss = await api("/sources");
    await onChange(ss.find((s: Obj) => s.id === source.id));
  }
  if (source.provider === "MANUAL")
    return (
      <div className="config-panel">
        <h3>Connect a supplier website</h3>
        <p>
          Save the website now. Agents open it in their own browser, log in
          normally, and enter verified supplier rates into a confirmed request.
          No browser automation or supplier password storage is used.
        </p>
        <Notice error={error} success={success} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api("/sources/" + source.id + "/manual-config", "PUT", {
                website_url: website,
                authorized,
                notes,
              });
              await refreshed();
              setSuccess(
                "Manual supplier activated. Open a request and use Enter supplier rates.",
              );
            });
          }}
        >
          <label>
            Supplier website URL
            <input
              type="url"
              required
              placeholder="https://supplier.example.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <label className="check-label wrapping">
            <input
              type="checkbox"
              checked={authorized}
              onChange={(e) => setAuthorized(e.target.checked)}
            />
            I confirm our agency is authorized to use this supplier and review
            its rates.
          </label>
          <button className="primary" disabled={busy || !authorized}>
            <Check size={15} />
            Save & activate manual supplier
          </button>
        </form>
      </div>
    );
  if (source.provider !== "JSON_API") return null;
  return (
    <div className="config-panel">
      <h3>Native JSON API connection</h3>
      <p>
        Use the supplier’s authorized search API documentation to configure its
        endpoint, request fields and response mapping. This runs directly from
        Atlas; a separate bridge is not needed.
      </p>
      <Notice error={error} success={success} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            const next = {
              ...cfg,
              request_template: JSON.parse(request),
              field_map: JSON.parse(mapping),
              static_fields: JSON.parse(statics),
              context_fields: contexts
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean),
            };
            const r = await api(
              "/sources/" + source.id + "/api-config",
              "PUT",
              {
                config: next,
                credential: credential || null,
                clear_credential: clear,
                notes,
              },
            );
            setCfg(r.config);
            setHasCredential(r.has_credential);
            setCredential("");
            setClear(false);
            await refreshed();
            setSuccess(
              "New version saved as draft. Run three different golden tests below, then activate.",
            );
          });
        }}
      >
        <label>
          HTTPS search endpoint
          <input
            type="url"
            required
            value={cfg.endpoint}
            placeholder="https://api.supplier.com/search"
            onChange={(e) => setCfg({ ...cfg, endpoint: e.target.value })}
          />
        </label>
        <div className="spec-grid">
          <label>
            HTTP method
            <select
              value={cfg.method}
              onChange={(e) => setCfg({ ...cfg, method: e.target.value })}
            >
              <option>POST</option>
              <option>GET</option>
            </select>
          </label>
          <label>
            Authentication
            <select
              value={cfg.auth_type}
              onChange={(e) => setCfg({ ...cfg, auth_type: e.target.value })}
            >
              <option value="BEARER">Bearer token</option>
              <option value="HEADER">Custom API-key header</option>
              <option value="NONE">No authentication</option>
            </select>
          </label>
          {cfg.auth_type === "HEADER" && (
            <label>
              API-key header name
              <input
                value={cfg.auth_header}
                onChange={(e) =>
                  setCfg({ ...cfg, auth_header: e.target.value })
                }
              />
            </label>
          )}
        </div>
        {cfg.auth_type !== "NONE" && (
          <label>
            Secret credential
            <input
              type="password"
              autoComplete="new-password"
              value={credential}
              placeholder={
                hasCredential
                  ? "Saved — leave blank to keep"
                  : "Paste supplier token / API key"
              }
              onChange={(e) => setCredential(e.target.value)}
            />
          </label>
        )}
        <label className="check-label">
          <input
            type="checkbox"
            checked={clear}
            onChange={(e) => setClear(e.target.checked)}
          />
          Remove saved credential
        </label>
        <label>
          Request body / GET query template (JSON)
          <textarea
            className="code-input"
            rows={7}
            value={request}
            onChange={(e) => setRequest(e.target.value)}
          />
        </label>
        <p className="field-hint">
          Use whole-value placeholders such as {"{{origin}}"},{" "}
          {"{{departure_date}}"}, {"{{adults}}"}. Match parameter names to the
          supplier’s API. Do not place secrets in the URL or template.
        </p>
        <div className="spec-grid">
          <label>
            Path to result array
            <input
              value={cfg.records_path}
              onChange={(e) => setCfg({ ...cfg, records_path: e.target.value })}
              placeholder="data.results (blank for root array)"
            />
          </label>
          <label>
            Rate validity (minutes)
            <input
              type="number"
              min={1}
              max={15}
              value={cfg.ttl_minutes}
              onChange={(e) =>
                setCfg({ ...cfg, ttl_minutes: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <label>
          Response field mapping (canonical name → JSON path)
          <textarea
            className="code-input"
            rows={8}
            value={mapping}
            onChange={(e) => setMapping(e.target.value)}
          />
        </label>
        <p className="field-hint">
          Example: “net_price”: “pricing.total”. Price must be the exact
          tax-inclusive total for all travelers, rooms and nights. This
          connector does not calculate per-person, nightly, currency, or tax
          conversions.
        </p>
        <label>
          Known supplier metadata (JSON)
          <textarea
            className="code-input"
            rows={3}
            value={statics}
            onChange={(e) => setStatics(e.target.value)}
          />
        </label>
        <label>
          Fields explicitly bound to the confirmed search
          <input
            value={contexts}
            onChange={(e) => setContexts(e.target.value)}
          />
        </label>
        <label className="check-label wrapping">
          <input
            type="checkbox"
            checked={cfg.scope_confirmed}
            onChange={(e) =>
              setCfg({ ...cfg, scope_confirmed: e.target.checked })
            }
          />
          I verified that every response row belongs to the requested route,
          dates, party and rooms. Otherwise I will map these fields from the
          response instead.
        </label>
        <label className="check-label wrapping">
          <input
            type="checkbox"
            checked={cfg.authorized_search_only}
            onChange={(e) =>
              setCfg({ ...cfg, authorized_search_only: e.target.checked })
            }
          />
          This is an authorized, search-only endpoint; it cannot book, cancel,
          hold, pay, or otherwise commit a transaction.
        </label>
        <label>
          Version notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button className="primary" disabled={busy}>
          <Save size={16} />
          Save connection & mapping version
        </button>
      </form>
    </div>
  );
}

export function ManualRatesPanel({
  request,
  sources,
  api,
  onSaved,
}: {
  request: Obj;
  sources: Obj[];
  api: API;
  onSaved: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false),
    [items, setItems] = useState<Obj[]>([]),
    [reviewed, setReviewed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const available = sources.filter(
    (s) => s.provider === "MANUAL" && s.status === "ACTIVE",
  );
  const kinds =
    request.spec.intent === "PACKAGE_SEARCH"
      ? ["FLIGHT", "HOTEL"]
      : request.spec.intent === "FLIGHT_SEARCH"
        ? ["FLIGHT"]
        : ["HOTEL"];
  function start() {
    setItems(
      kinds.map((kind) => ({
        source_id: available.find((s) => s.kind === kind)?.id || "",
        title: "",
        external_id: "",
        net_price: "",
        currency: "USD",
        details: "",
        cancellation_policy: "",
        stops: 0,
        stars: kind === "HOTEL" ? request.spec.stars_min : 0,
        ttl_minutes: 5,
      })),
    );
    setExpanded(true);
    setReviewed(false);
    setError("");
  }
  function set(i: number, key: string, value: any) {
    setItems((old) =>
      old.map((r, n) => (n === i ? { ...r, [key]: value } : r)),
    );
    setReviewed(false);
  }
  if (!available.length) return null;
  return (
    <section className="card manual-rates">
      <div className="section-title">
        <FileText size={18} />
        <strong>Verified manual supplier rates</strong>
      </div>
      <p>
        For supplier websites without a connected API. Enter rates you have just
        verified in the supplier portal; Atlas tracks their source and your
        review.
      </p>
      {!expanded ? (
        <button
          className="secondary"
          disabled={
            request.confirmed_revision !== request.revision ||
            request.status === "SEARCHING" ||
            ["WON", "LOST", "CANCELLED"].includes(request.status)
          }
          onClick={start}
        >
          <Plus size={16} />
          Enter supplier rates
        </button>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await api("/requests/" + request.id + "/manual-results", "POST", {
                revision: request.revision,
                reviewed,
                items,
              });
              setExpanded(false);
              await onSaved();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {items.map((item, i) => {
            const source = available.find((s) => s.id === item.source_id);
            return (
              <div className="manual-rate-item" key={i}>
                <h3>
                  {kinds[i] === "FLIGHT" ? "Flight rate" : "Hotel rate"} ·{" "}
                  {request.spec.origin} → {request.spec.destination}
                </h3>
                <label>
                  Supplier
                  <select
                    required
                    value={item.source_id}
                    onChange={(e) => set(i, "source_id", e.target.value)}
                  >
                    <option value="">Select a manual supplier</option>
                    {available
                      .filter((s) => s.kind === kinds[i])
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                  </select>
                </label>
                {source?.website_url && (
                  <a
                    className="text-button"
                    href={source.website_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open supplier website <ArrowUpRight size={15} />
                  </a>
                )}
                <div className="spec-grid">
                  <label>
                    Rate title
                    <input
                      required
                      value={item.title}
                      onChange={(e) => set(i, "title", e.target.value)}
                    />
                  </label>
                  <label>
                    Supplier rate / offer reference
                    <input
                      required
                      value={item.external_id}
                      onChange={(e) => set(i, "external_id", e.target.value)}
                    />
                  </label>
                  <label>
                    Total including taxes
                    <input
                      required
                      type="number"
                      min="0.001"
                      step="0.001"
                      value={item.net_price}
                      onChange={(e) => set(i, "net_price", e.target.value)}
                    />
                  </label>
                  <label>
                    Currency
                    <select
                      value={item.currency}
                      onChange={(e) => set(i, "currency", e.target.value)}
                    >
                      {["USD", "EUR", "AED", "OMR", "IRR", "GBP"].map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {kinds[i] === "FLIGHT" ? "Stops" : "Hotel stars"}
                    <input
                      type="number"
                      min={0}
                      max={5}
                      value={kinds[i] === "FLIGHT" ? item.stops : item.stars}
                      onChange={(e) =>
                        set(
                          i,
                          kinds[i] === "FLIGHT" ? "stops" : "stars",
                          Number(e.target.value),
                        )
                      }
                    />
                  </label>
                  <label>
                    Valid for (minutes)
                    <input
                      type="number"
                      min={1}
                      max={15}
                      value={item.ttl_minutes}
                      onChange={(e) =>
                        set(i, "ttl_minutes", Number(e.target.value))
                      }
                    />
                  </label>
                </div>
                <label>
                  Exact itinerary / room, meal and baggage details
                  <textarea
                    required
                    value={item.details}
                    onChange={(e) => set(i, "details", e.target.value)}
                  />
                </label>
                <label>
                  Supplier cancellation / change conditions
                  <textarea
                    required
                    value={item.cancellation_policy}
                    onChange={(e) =>
                      set(i, "cancellation_policy", e.target.value)
                    }
                  />
                </label>
              </div>
            );
          })}
          <label className="check-label wrapping">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I just verified availability, the exact route and dates, all{" "}
            {request.spec.adults} adults, all {request.spec.rooms} room(s), the
            total for the entire trip/stay including taxes, and supplier terms.
            These are real supplier rates, not estimates.
          </label>
          <div className="panel-actions">
            <button className="primary" disabled={busy || !reviewed}>
              <Check size={15} />
              Save verified rates
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setExpanded(false)}
            >
              Cancel
            </button>
          </div>
          <p className="field-hint">
            Saving creates a new current result set. Previous search rates
            remain in history and cannot be mixed with this set.
          </p>
        </form>
      )}
    </section>
  );
}
