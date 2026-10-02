import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Plane,
  Hotel,
  ArrowUpRight,
  ArrowRight,
  Plus,
  Search,
  Settings,
  Layers3,
  LayoutDashboard,
  BarChart3,
  LogOut,
  ChevronRight,
  Check,
  X,
  Loader2,
  ShieldCheck,
  Mic,
  RefreshCw,
  FileText,
  Clock,
  CircleHelp,
  Command,
  CircleCheck,
  AlertTriangle,
  Users,
  Download,
  Globe2,
  SlidersHorizontal,
  Send,
  Play,
  CircleDot,
} from "lucide-react";
import "./styles.css";
import {
  AISettingsPanel,
  SourceConfigPanel,
  ManualRatesPanel,
} from "./ConfigPanels";

type Obj = Record<string, any>;
const airports: Record<string, string> = {
  IKA: "Tehran Imam Khomeini",
  THR: "Tehran Mehrabad",
  MCT: "Muscat",
  DXB: "Dubai",
  IST: "Istanbul",
  DOH: "Doha",
  AUH: "Abu Dhabi",
  LHR: "London Heathrow",
  CDG: "Paris Charles de Gaulle",
  MHD: "Mashhad",
  SYZ: "Shiraz",
  TBS: "Tbilisi",
  GYD: "Baku",
};
const datePlus = (days: number) =>
  new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
const freshSpec = () => ({
  intent: "PACKAGE_SEARCH",
  origin: "IKA",
  destination: "MCT",
  departure_date: datePlus(14),
  return_date: datePlus(18),
  adults: 2,
  children: 0,
  rooms: 1,
  stars_min: 4,
  direct_only: true,
  cabin: "ECONOMY",
});
const money = (n: any, c = "USD") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: c,
    maximumFractionDigits: c === "OMR" ? 3 : 2,
  }).format(Number(n));
const label = (s: string) =>
  s
    ?.replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());
const time = (s: string) =>
  new Date(s).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
async function api(path: string, method = "GET", body?: any) {
  const headers: Record<string, string> = { "X-Requested-With": "Atlas" };
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  if (method === "POST") headers["Idempotency-Key"] = crypto.randomUUID();
  const r = await fetch("/api" + path, {
    method,
    headers,
    credentials: "same-origin",
    body:
      body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
function Badge({ value }: { value: string }) {
  return (
    <span
      className={
        "badge " +
        (value?.includes("FAIL") || value === "RECONNECT_REQUIRED"
          ? "bad"
          : value === "ACTIVE" ||
              value === "APPROVED" ||
              value === "SUCCESS" ||
              value === "WON"
            ? "good"
            : "")
      }
    >
      {label(value)}
    </span>
  );
}
function App() {
  const [user, setUser] = useState<Obj | null>(null),
    [boot, setBoot] = useState(true),
    [page, setPage] = useState("desk"),
    [fa, setFa] = useState(false),
    [toast, setToast] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [requests, setRequests] = useState<Obj[]>([]),
    [sources, setSources] = useState<Obj[]>([]),
    [settings, setSettings] = useState<Obj>({}),
    [metrics, setMetrics] = useState<Obj>({}),
    [current, setCurrent] = useState<Obj | null>(null),
    [spec, setSpec] = useState<Obj>(freshSpec()),
    [newModal, setNewModal] = useState(false),
    [customer, setCustomer] = useState(""),
    [command, setCommand] = useState(""),
    [selection, setSelection] = useState<Record<string, string>>({}),
    [chosenSources, setChosenSources] = useState<string[]>([]),
    [markup, setMarkup] = useState("10"),
    [markupType, setMarkupType] = useState("PERCENT"),
    [note, setNote] = useState(""),
    [tab, setTab] = useState("FLIGHT"),
    [query, setQuery] = useState(""),
    [sort, setSort] = useState("price"),
    [printOffer, setPrintOffer] = useState<Obj | null>(null);
  const t = (en: string, persian: string) => (fa ? persian : en);
  useEffect(() => {
    api("/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setBoot(false));
  }, []);
  useEffect(() => {
    document.documentElement.lang = fa ? "fa" : "en";
    document.documentElement.dir = fa ? "rtl" : "ltr";
  }, [fa]);
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(id);
    }
  }, [toast]);
  async function load() {
    const [rs, ss, st, mt] = await Promise.all([
      api("/requests"),
      api("/sources"),
      api("/settings"),
      api("/metrics"),
    ]);
    setRequests(rs);
    setSources(ss);
    setSettings(st);
    setMetrics(mt);
  }
  useEffect(() => {
    if (user) load().catch((e) => setError(e.message));
  }, [user]);
  async function open(id: string, reset = true) {
    const r = await api("/requests/" + id);
    setCurrent(r);
    if (reset) {
      setSpec(r.spec);
      setSelection({});
      setCommand("");
      setTab(r.spec.intent === "HOTEL_SEARCH" ? "HOTEL" : "FLIGHT");
    }
    return r;
  }
  useEffect(() => {
    if (!current || current.status !== "SEARCHING") return;
    const id = setInterval(() => {
      open(current.id, false)
        .then((r) => {
          if (r.status !== "SEARCHING") load();
        })
        .catch((e) => setError(e.message));
    }, 1200);
    return () => clearInterval(id);
  }, [current?.id, current?.status]);
  async function action(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function create(e: React.FormEvent) {
    e.preventDefault();
    await action(async () => {
      const r = await api("/requests", "POST", {
        customer_name: customer,
        spec: freshSpec(),
      });
      await open(r.id);
      await load();
      setNewModal(false);
      setCustomer("");
      setPage("desk");
      setToast("Request created. Review travel details to continue.");
    });
  }
  async function confirm() {
    if (!current) return;
    await action(async () => {
      await api(`/requests/${current.id}/confirm`, "POST", {
        spec,
        revision: current.revision,
      });
      await open(current.id);
      await load();
      setToast("Travel details confirmed.");
    });
  }
  async function understand(e: React.FormEvent) {
    e.preventDefault();
    if (!current || !command.trim()) return;
    await action(async () => {
      const r = await api(`/requests/${current.id}/messages`, "POST", {
        text: command,
      });
      setSpec(r.spec);
      await open(current.id);
      await load();
      setCommand("");
      setSelection({});
      setToast("Review the extracted fields, then confirm.");
    });
  }
  const activeSources = sources.filter(
    (s) =>
      s.status === "ACTIVE" &&
      s.provider !== "MANUAL" &&
      (spec.intent === "PACKAGE_SEARCH" ||
        s.kind === (spec.intent === "HOTEL_SEARCH" ? "HOTEL" : "FLIGHT")),
  );
  useEffect(() => {
    const demos = activeSources.filter((s) => s.provider === "DEMO");
    setChosenSources((demos.length ? demos : activeSources).map((s) => s.id));
  }, [sources, spec.intent]);
  const currentRates = (current?.results || []).filter(
    (r: Obj) => r.run_id === current?.active_run_id,
  );
  const selected = currentRates.filter((r: Obj) =>
    Object.values(selection).includes(r.id),
  );
  const totalNet = selected.reduce(
    (sum: number, r: Obj) => sum + Number(r.net_price),
    0,
  );
  const margin =
    markupType === "PERCENT"
      ? (totalNet * Number(markup || 0)) / 100
      : Number(markup || 0);
  const isConfirmed =
    !!current &&
    current.confirmed_revision === current.revision &&
    JSON.stringify(spec) === JSON.stringify(current.spec);
  const dirty =
    current && JSON.stringify(spec) !== JSON.stringify(current.spec);
  const expected = spec.intent === "PACKAGE_SEARCH" ? 2 : 1;
  const closed = ["WON", "LOST", "CANCELLED"].includes(current?.status);
  const run = current?.runs?.find((r: Obj) => r.id === current.active_run_id);
  async function start() {
    if (!current) return;
    await action(async () => {
      await api(`/requests/${current.id}/search-runs`, "POST", {
        source_ids: chosenSources,
      });
      setSelection({});
      await open(current.id, false);
      await load();
    });
  }
  async function draft() {
    if (!current) return;
    await action(async () => {
      await api("/offers", "POST", {
        request_id: current.id,
        result_ids: selected.map((r: Obj) => r.id),
        markup_type: markupType,
        markup,
        note,
      });
      await open(current.id, false);
      await load();
      setToast("Offer draft saved. Review and approve it below.");
    });
  }
  async function voice(file: File) {
    if (!current) return;
    await action(async () => {
      const form = new FormData();
      form.append("file", file);
      const out = await api(`/requests/${current.id}/voice`, "POST", form);
      setCommand(out.transcript);
      setToast("Transcript ready. Review it before extracting details.");
    });
  }
  if (boot)
    return (
      <div className="boot">
        <Loader2 className="spin" /> Opening workspace…
      </div>
    );
  if (!user) return <Login onLogin={setUser} />;
  const nav = [
    ["desk", LayoutDashboard, t("Search desk", "میز جست‌وجو")],
    ["requests", Layers3, t("Requests", "درخواست‌ها")],
    ["sources", Globe2, t("Source studio", "منابع")],
    ["insights", BarChart3, t("Insights", "گزارش‌ها")],
    ["settings", Settings, t("Settings", "تنظیمات")],
  ] as const;
  return (
    <>
      <div className="app-shell">
        <aside className="sidebar">
          <a
            className="brand"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setPage("desk");
            }}
          >
            <div className="brand-symbol">
              A<span>✦</span>
            </div>
            <div>
              atlas<span>TRAVEL COPILOT</span>
            </div>
          </a>
          <div className="agency">
            <span className="agency-icon">
              <Globe2 size={17} />
            </span>
            <div>
              {t("Agency workspace", "فضای کاری آژانس")}
              <small>{t("Local workspace · v0.2", "نسخه آزمایشی محلی")}</small>
            </div>
            <CircleDot size={13} />
          </div>
          <div className="nav-caption">{t("WORKSPACE", "فضای کاری")}</div>
          <nav>
            {nav.map(([id, Icon, name]) => (
              <button
                key={id}
                className={page === id ? "active" : ""}
                onClick={() => setPage(id)}
              >
                <Icon size={19} />
                {name}
                {id === "requests" && <span>{requests.length}</span>}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="guard">
              <ShieldCheck size={23} />
              <strong>
                {t("You stay in control", "تصمیم نهایی با شماست")}
              </strong>
              <p>
                {t(
                  "Review every request. Approve every offer.",
                  "هر درخواست را بررسی و هر پیشنهاد را تأیید کنید.",
                )}
              </p>
            </div>
            <button
              className="user"
              onClick={() =>
                action(async () => {
                  await api("/auth/logout", "POST");
                  setUser(null);
                  setCurrent(null);
                })
              }
            >
              <span className="avatar">
                {user.name.slice(0, 2).toUpperCase()}
              </span>
              <span>
                {user.name}
                <small>{label(user.role)}</small>
              </span>
              <LogOut size={17} />
            </button>
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="breadcrumbs">
              {t("Workspace", "فضای کاری")}
              <ChevronRight size={14} />
              <strong>{nav.find((n) => n[0] === page)?.[2]}</strong>
            </div>
            <div className="header-actions">
              <span className="local-status">
                <i />
                {t("Local workspace", "فضای کاری محلی")}
              </span>
              <button
                className="icon-button language"
                onClick={() => setFa(!fa)}
                title="Change language"
              >
                {fa ? "EN" : "فا"}
              </button>
              <button
                className="icon-button"
                onClick={() => setPage("settings")}
                title="Setup and help"
              >
                <CircleHelp size={19} />
              </button>
              <span className="avatar small">{user.name.slice(0, 1)}</span>
            </div>
          </header>
          <main className="content">
            <div className="page-heading">
              <div>
                <div className="eyebrow">
                  {t(
                    "YOUR TRAVEL OPERATIONS, TOGETHER",
                    "عملیات سفر، در یک فضای کاری",
                  )}
                </div>
                <h1>
                  {page === "desk"
                    ? t(
                        "A better way to get there.",
                        "راهی بهتر برای برنامه‌ریزی سفر.",
                      )
                    : nav.find((n) => n[0] === page)?.[2]}
                </h1>
                <p>
                  {page === "desk"
                    ? t(
                        "Turn a travel request into a considered offer.",
                        "درخواست سفر را به یک پیشنهاد بررسی‌شده تبدیل کنید.",
                      )
                    : page === "sources"
                      ? t(
                          "Connect, test, and activate the sources your agency trusts.",
                          "منابع آژانس را متصل، آزمایش و فعال کنید.",
                        )
                      : page === "requests"
                        ? t(
                            "Every customer journey, from first request to final decision.",
                            "هر سفر مشتری، از اولین درخواست تا تصمیم نهایی.",
                          )
                        : page === "insights"
                          ? t(
                              "Actual workspace activity. Demo searches are counted separately.",
                              "عملکرد واقعی محیط کاری؛ جست‌وجوهای نمونه جداگانه شمارش می‌شوند.",
                            )
                          : t(
                              "Manage your team and prepare your live integrations.",
                              "مدیریت تیم و آماده‌سازی اتصال‌های واقعی.",
                            )}
                </p>
              </div>
              <button className="primary" onClick={() => setNewModal(true)}>
                <Plus size={17} />
                {t("New request", "درخواست جدید")}
              </button>
            </div>
            {error && (
              <div role="alert" className="error global-error">
                <AlertTriangle size={18} />
                <span>{error}</span>
                <button onClick={() => setError("")} aria-label="Dismiss error">
                  <X size={16} />
                </button>
              </div>
            )}
            {page === "desk" && (
              <>
                <div className="stats-strip">
                  <div>
                    <span>{t("Open requests", "درخواست‌های باز")}</span>
                    <strong>
                      {metrics.open || 0}
                      <small>{t("in your workspace", "در فضای کاری")}</small>
                    </strong>
                  </div>
                  <div>
                    <span>{t("Approved offers", "پیشنهادهای تأییدشده")}</span>
                    <strong>
                      {metrics.approved_offers || 0}
                      <small>
                        {t("human reviewed", "بررسی‌شده توسط کارشناس")}
                      </small>
                    </strong>
                  </div>
                  <div>
                    <span>{t("Active sources", "منابع فعال")}</span>
                    <strong>
                      {sources.filter((s) => s.status === "ACTIVE").length}
                      <small>
                        {sources.filter((s) => s.provider === "DEMO").length}{" "}
                        {t("demo sources", "منبع نمونه")}
                      </small>
                    </strong>
                  </div>
                  <div>
                    <span>{t("Search success", "موفقیت جست‌وجو")}</span>
                    <strong>
                      {metrics.search_success_pct == null
                        ? "—"
                        : metrics.search_success_pct + "%"}
                      <small>{t("completed runs", "اجراهای تکمیل‌شده")}</small>
                    </strong>
                  </div>
                </div>
                {!current ? (
                  <div className="welcome card">
                    <div className="welcome-mark">
                      <Plane size={34} />
                    </div>
                    <span className="eyebrow">
                      {t("START WITH A REQUEST", "از یک درخواست شروع کنید")}
                    </span>
                    <h2>
                      {t(
                        "Where are your customers headed?",
                        "مقصد بعدی مشتریان شما کجاست؟",
                      )}
                    </h2>
                    <p>
                      {t(
                        "Describe the trip in English or Persian, compare flight and hotel sources, then build an offer with your own markup.",
                        "سفر را به فارسی یا انگلیسی شرح دهید، پرواز و هتل را مقایسه کنید و پیشنهاد قیمت بسازید.",
                      )}
                    </p>
                    <button
                      className="primary"
                      onClick={() => setNewModal(true)}
                    >
                      <Plus size={17} />
                      {t("Create your first request", "ساخت درخواست سفر")}
                    </button>
                    {!sources.length && user.role === "ADMIN" && (
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() =>
                          action(async () => {
                            await api("/demo/setup", "POST");
                            await load();
                            setToast(
                              "Four clearly labelled demo sources are ready.",
                            );
                          })
                        }
                      >
                        Load demonstration sources <ArrowRight size={15} />
                      </button>
                    )}
                    <div className="welcome-foot">
                      <ShieldCheck size={16} />{" "}
                      {t(
                        "No automatic bookings. Final decisions stay with your team.",
                        "رزرو خودکار انجام نمی‌شود؛ تصمیم نهایی با تیم شماست.",
                      )}
                    </div>
                    {requests.length > 0 && (
                      <div className="recent">
                        <span>CONTINUE A REQUEST</span>
                        {requests.slice(0, 3).map((r) => (
                          <button
                            key={r.id}
                            onClick={() =>
                              action(async () => {
                                await open(r.id);
                              })
                            }
                          >
                            {r.customer_name}{" "}
                            <span>
                              {r.spec.origin} → {r.spec.destination}
                            </span>
                            <ArrowUpRight size={16} />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="case-bar">
                      <div>
                        <span className="case-id">
                          {current.id.slice(-6).toUpperCase()}
                        </span>
                        <strong>{current.customer_name}</strong>
                        <Badge value={current.status} />
                      </div>
                      <div>
                        <span>{current.owner_name}</span>
                        <button
                          className="icon-button"
                          title="Refresh request"
                          onClick={() =>
                            action(async () => {
                              await open(current.id);
                              await load();
                            })
                          }
                        >
                          <RefreshCw size={15} />
                        </button>
                        <button
                          className="text-button"
                          onClick={() => setCurrent(null)}
                        >
                          Close <X size={14} />
                        </button>
                      </div>
                    </div>
                    <div className="desk-layout">
                      <div className="desk-main">
                        <section className="composer card">
                          <div className="section-title">
                            <span className="spark">✦</span>
                            <strong>
                              {t("Tell your copilot", "به دستیار بگویید")}
                            </strong>
                            <span className="muted">
                              {settings.ai_provider === "GEMINI"
                                ? "Gemini connected"
                                : "Offline field extraction"}
                            </span>
                          </div>
                          <form onSubmit={understand}>
                            <textarea
                              dir="auto"
                              aria-label="Travel request"
                              placeholder={t(
                                `Try “2 adults Tehran to Muscat, ${datePlus(14)} to ${datePlus(18)}, direct flights, 4 star hotel”`,
                                "مثلاً: دو نفر تهران به مسقط، پرواز مستقیم و هتل ۴ ستاره",
                              )}
                              value={command}
                              onChange={(e) => setCommand(e.target.value)}
                              disabled={closed}
                            />
                            <div className="composer-bottom">
                              <span>
                                <ShieldCheck size={14} />
                                {t(
                                  "Your confirmation is required before searching",
                                  "تأیید شما پیش از جست‌وجو الزامی است",
                                )}
                              </span>
                              <div>
                                <label
                                  className={
                                    "icon-button upload " +
                                    (!settings.voice_enabled ? "disabled" : "")
                                  }
                                  title={
                                    settings.voice_enabled
                                      ? "Audio is sent to Gemini. Choose a file only if approved by your agency."
                                      : "Configure Gemini to enable voice"
                                  }
                                >
                                  <Mic size={18} />
                                  <input
                                    type="file"
                                    accept="audio/*"
                                    disabled={
                                      !settings.voice_enabled || busy || closed
                                    }
                                    onChange={(e) => {
                                      if (e.target.files?.[0])
                                        void voice(e.target.files[0]);
                                      e.target.value = "";
                                    }}
                                  />
                                </label>
                                <button
                                  className="send"
                                  type="submit"
                                  disabled={!command.trim() || busy || closed}
                                  aria-label="Extract travel details"
                                >
                                  {busy ? (
                                    <Loader2 size={17} className="spin" />
                                  ) : (
                                    <ArrowRight size={18} />
                                  )}
                                </button>
                              </div>
                            </div>
                          </form>
                          {current.messages.length > 0 && (
                            <details className="messages">
                              <summary>
                                {t("Conversation history", "تاریخچه گفتگو")} ·{" "}
                                {current.messages.length}
                              </summary>
                              {current.messages.map((m: Obj, i: number) => (
                                <div key={i} className={"message " + m.role}>
                                  <strong>
                                    {m.role === "user"
                                      ? t("Agent", "کارشناس")
                                      : t("Copilot", "دستیار")}
                                  </strong>
                                  <p dir="auto">{m.text}</p>
                                </div>
                              ))}
                            </details>
                          )}
                        </section>
                        <section className="card trip-card">
                          <div className="section-title">
                            <SlidersHorizontal size={17} />
                            <strong>{t("Travel details", "جزئیات سفر")}</strong>
                            <span
                              className={
                                "detail-state " +
                                (isConfirmed ? "confirmed" : "")
                              }
                            >
                              {isConfirmed ? (
                                <>
                                  <Check size={14} /> Confirmed
                                </>
                              ) : (
                                "Review required"
                              )}
                            </span>
                          </div>
                          <fieldset disabled={closed || busy}>
                            <SpecForm spec={spec} setSpec={setSpec} fa={fa} />
                          </fieldset>
                          <div className="form-footer">
                            <span>
                              {t(
                                "Gregorian dates · total party pricing",
                                "تاریخ میلادی · قیمت کل مسافران",
                              )}
                              {spec.children > 0 && " · Adult-only pilot"}
                            </span>
                            <button
                              className="secondary"
                              disabled={busy || closed || isConfirmed}
                              onClick={confirm}
                            >
                              <Check size={15} />
                              {t("Confirm details", "تأیید جزئیات")}
                            </button>
                          </div>
                        </section>
                        <section className="card source-picker">
                          <div className="section-title">
                            <Globe2 size={17} />
                            <strong>
                              {t("Search your sources", "جست‌وجو در منابع")}
                            </strong>
                            <span className="muted">
                              {chosenSources.length} selected
                            </span>
                          </div>
                          <div className="source-chips">
                            {activeSources.map((s) => (
                              <label
                                key={s.id}
                                className={
                                  chosenSources.includes(s.id) ? "picked" : ""
                                }
                              >
                                <input
                                  type="checkbox"
                                  checked={chosenSources.includes(s.id)}
                                  onChange={() =>
                                    setChosenSources((v) =>
                                      v.includes(s.id)
                                        ? v.filter((id) => id !== s.id)
                                        : [...v, s.id],
                                    )
                                  }
                                />
                                {s.kind === "FLIGHT" ? (
                                  <Plane size={14} />
                                ) : (
                                  <Hotel size={14} />
                                )}
                                <span>{s.name}</span>
                              </label>
                            ))}
                            {!activeSources.length && (
                              <p className="muted">
                                No active sources.{" "}
                                <button
                                  className="text-button"
                                  onClick={() => setPage("sources")}
                                >
                                  Open Source Studio
                                </button>
                              </p>
                            )}
                          </div>
                          <div className="search-footer">
                            <span>
                              <Clock size={14} />
                              {t(
                                "Fresh rates expire after 15 minutes or sooner",
                                "اعتبار نرخ‌ها حداکثر ۱۵ دقیقه است",
                              )}
                            </span>
                            <button
                              className="primary"
                              disabled={
                                !isConfirmed ||
                                !chosenSources.length ||
                                busy ||
                                current.status === "SEARCHING" ||
                                closed
                              }
                              onClick={start}
                            >
                              {current.status === "SEARCHING" ? (
                                <Loader2 className="spin" size={17} />
                              ) : (
                                <Search size={17} />
                              )}{" "}
                              {t("Search sources", "جست‌وجوی منابع")}
                            </button>
                          </div>
                        </section>
                        {!dirty && (
                          <ManualRatesPanel
                            key={current.id + ":" + current.revision}
                            request={current}
                            sources={sources}
                            api={api}
                            onSaved={async () => {
                              setSelection({});
                              await open(current.id, false);
                              await load();
                              setToast("Verified manual rates saved.");
                            }}
                          />
                        )}
                        {run && (
                          <section className="results-section">
                            <div className="results-heading">
                              <div>
                                <h2>
                                  {t(
                                    "Your shortlist starts here",
                                    "گزینه‌های سفر شما",
                                  )}{" "}
                                  <span>{currentRates.length}</span>
                                </h2>
                                <p>
                                  {t(
                                    "Compare like-for-like. Choose one option for each service.",
                                    "گزینه‌ها را مقایسه و برای هر خدمت یک مورد انتخاب کنید.",
                                  )}
                                </p>
                              </div>
                              <select
                                aria-label="Sort results"
                                value={sort}
                                onChange={(e) => setSort(e.target.value)}
                              >
                                <option value="price">
                                  Price: low to high
                                </option>
                                <option value="source">Source name</option>
                              </select>
                            </div>
                            <div className="jobs">
                              {run.jobs.map((j: Obj) => (
                                <span
                                  key={j.job_id}
                                  title={j.error_code || j.status}
                                >
                                  {["QUEUED", "RUNNING"].includes(j.status) ? (
                                    <Loader2 size={12} className="spin" />
                                  ) : j.status === "SUCCESS" ? (
                                    <CircleCheck size={12} />
                                  ) : (
                                    <AlertTriangle size={12} />
                                  )}{" "}
                                  {j.source_name}
                                  <small>{label(j.status)}</small>
                                </span>
                              ))}
                            </div>
                            {currentRates.some((r: Obj) => r.demo) && (
                              <div className="demo-banner">
                                <AlertTriangle size={15} />
                                {t(
                                  "DEMO RESULTS — synthetic prices and itineraries. Not bookable.",
                                  "نتایج نمونه — قیمت‌ها و برنامه سفر ساختگی و غیرقابل رزرو هستند.",
                                )}
                              </div>
                            )}
                            <div className="result-tabs">
                              {["FLIGHT", "HOTEL"]
                                .filter(
                                  (k) =>
                                    spec.intent === "PACKAGE_SEARCH" ||
                                    k ===
                                      (spec.intent === "HOTEL_SEARCH"
                                        ? "HOTEL"
                                        : "FLIGHT"),
                                )
                                .map((k) => (
                                  <button
                                    className={tab === k ? "active" : ""}
                                    onClick={() => setTab(k)}
                                    key={k}
                                  >
                                    {k === "FLIGHT" ? (
                                      <Plane size={16} />
                                    ) : (
                                      <Hotel size={16} />
                                    )}{" "}
                                    {k === "FLIGHT"
                                      ? t("Flights", "پروازها")
                                      : t("Hotels", "هتل‌ها")}
                                    <span>
                                      {
                                        currentRates.filter(
                                          (r: Obj) => r.kind === k,
                                        ).length
                                      }
                                    </span>
                                  </button>
                                ))}
                            </div>
                            {[...currentRates]
                              .filter((r: Obj) => r.kind === tab)
                              .sort((a: Obj, b: Obj) =>
                                sort === "source"
                                  ? a.source_name.localeCompare(b.source_name)
                                  : a.currency.localeCompare(b.currency) ||
                                    Number(a.net_price) - Number(b.net_price),
                              )
                              .map((rate: Obj, i: number) => (
                                <RateCard
                                  key={rate.id}
                                  rate={rate}
                                  selected={selection[rate.kind] === rate.id}
                                  best={i === 0 && sort === "price"}
                                  disabled={!!dirty || !isConfirmed || closed}
                                  onSelect={() =>
                                    setSelection((v) => ({
                                      ...v,
                                      [rate.kind]:
                                        v[rate.kind] === rate.id ? "" : rate.id,
                                    }))
                                  }
                                />
                              ))}
                            {!currentRates.filter((r: Obj) => r.kind === tab)
                              .length && (
                              <div className="empty-results">
                                {current.status === "SEARCHING" ? (
                                  <>
                                    <Loader2 className="spin" size={22} />
                                    <p>
                                      Searching sources… Results appear as each
                                      source finishes.
                                    </p>
                                  </>
                                ) : (
                                  <>
                                    <Search size={25} />
                                    <p>
                                      No validated results for this service.
                                      Check source status or search again.
                                    </p>
                                  </>
                                )}
                              </div>
                            )}
                          </section>
                        )}
                        <section className="card activity">
                          <details>
                            <summary>
                              <Clock size={15} />{" "}
                              {t(
                                "Activity & search history",
                                "فعالیت‌ها و تاریخچه جست‌وجو",
                              )}{" "}
                              <span>{current.activity.length} events</span>
                            </summary>
                            <div className="run-history">
                              {current.runs.map((r: Obj) => (
                                <div key={r.id}>
                                  <span>
                                    {time(r.created_at)} · Revision {r.revision}
                                  </span>
                                  <Badge value={r.status} />
                                </div>
                              ))}
                            </div>
                            {current.activity.map((a: Obj, i: number) => (
                              <div className="activity-row" key={i}>
                                <i />
                                <div>
                                  <strong>{label(a.event)}</strong>
                                  <small>
                                    {time(a.created)} · {a.actor.slice(-6)}
                                  </small>
                                </div>
                              </div>
                            ))}
                          </details>
                        </section>
                      </div>
                      <aside className="offer-column">
                        <section className="card offer-builder">
                          <div className="section-title">
                            <FileText size={18} />
                            <strong>
                              {t("Build an offer", "ساخت پیشنهاد قیمت")}
                            </strong>
                          </div>
                          <p className="muted">
                            {t(
                              "Your expertise. Your final price.",
                              "تخصص شما، قیمت نهایی شما.",
                            )}
                          </p>
                          {selected.length === 0 ? (
                            <div className="offer-empty">
                              <Layers3 size={30} />
                              <p>
                                {t(
                                  "Select a flight or hotel to start your offer.",
                                  "برای شروع، پرواز یا هتل انتخاب کنید.",
                                )}
                              </p>
                            </div>
                          ) : (
                            <div className="selected-rates">
                              {selected.map((r: Obj) => (
                                <div key={r.id}>
                                  <span className="selected-icon">
                                    {r.kind === "FLIGHT" ? (
                                      <Plane size={17} />
                                    ) : (
                                      <Hotel size={17} />
                                    )}
                                  </span>
                                  <div>
                                    <strong>{r.title}</strong>
                                    <small>{r.source_name}</small>
                                    <b>{money(r.net_price, r.currency)}</b>
                                  </div>
                                  <button
                                    className="icon-button"
                                    aria-label="Remove rate"
                                    onClick={() =>
                                      setSelection((v) => ({
                                        ...v,
                                        [r.kind]: "",
                                      }))
                                    }
                                  >
                                    <X size={14} />
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="pricing">
                            <div>
                              <span>{t("Net total", "مجموع خالص")}</span>
                              <strong>
                                {money(totalNet, selected[0]?.currency)}
                              </strong>
                            </div>
                            <label>
                              {t("Your markup", "سود شما")}
                              <span className="markup-input">
                                <input
                                  aria-label="Markup amount"
                                  type="number"
                                  min="0"
                                  max={markupType === "PERCENT" ? 100 : 100000}
                                  step="0.01"
                                  value={markup}
                                  onChange={(e) => setMarkup(e.target.value)}
                                />
                                <select
                                  aria-label="Markup type"
                                  value={markupType}
                                  onChange={(e) =>
                                    setMarkupType(e.target.value)
                                  }
                                >
                                  <option value="PERCENT">%</option>
                                  <option value="FIXED">Fixed</option>
                                </select>
                              </span>
                            </label>
                            <div className="margin-line">
                              <span>{t("Margin", "سود")}</span>
                              <span>
                                {money(margin, selected[0]?.currency)}
                              </span>
                            </div>
                            <div className="final-total">
                              <span>{t("Customer total", "مبلغ مشتری")}</span>
                              <strong>
                                {money(
                                  totalNet + margin,
                                  selected[0]?.currency,
                                )}
                              </strong>
                            </div>
                            <small>
                              {t(
                                "Preview only. Server calculates and validates the saved total.",
                                "محاسبه نهایی و اعتبارسنجی هنگام ذخیره انجام می‌شود.",
                              )}
                            </small>
                          </div>
                          <textarea
                            aria-label="Offer note"
                            className="note"
                            rows={2}
                            maxLength={1000}
                            placeholder={t(
                              "Add a customer-facing note…",
                              "یادداشت برای مشتری…",
                            )}
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                          />
                          <button
                            className="primary wide"
                            disabled={
                              selected.length !== expected ||
                              busy ||
                              !isConfirmed ||
                              closed ||
                              !Number.isFinite(Number(markup)) ||
                              Number(markup) < 0
                            }
                            onClick={draft}
                          >
                            <FileText size={16} />
                            {t("Create draft offer", "ذخیره پیش‌نویس")}
                          </button>
                          <div className="approval-foot">
                            <ShieldCheck size={14} />
                            {t(
                              "Human approval before export",
                              "تأیید انسانی پیش از خروجی",
                            )}
                          </div>
                        </section>
                        {(current.offers || []).map((off: Obj) => (
                          <section className="card saved-offer" key={off.id}>
                            <div className="section-title">
                              <strong>
                                {t("Offer", "پیشنهاد")} #
                                {off.id.slice(-5).toUpperCase()}
                              </strong>
                              <Badge value={off.status} />
                            </div>
                            {off.demo && (
                              <span className="demo-text">
                                DEMO · NOT BOOKABLE
                              </span>
                            )}
                            <strong className="offer-amount">
                              {money(off.total, off.currency)}
                            </strong>
                            <p>
                              {off.items.map((r: Obj) => r.title).join(" + ")}
                            </p>
                            {off.status === "DRAFT" ? (
                              <button
                                className="secondary wide"
                                disabled={busy || closed}
                                onClick={() =>
                                  action(async () => {
                                    await api(
                                      "/offers/" + off.id + "/approve",
                                      "POST",
                                    );
                                    await open(current.id, false);
                                    await load();
                                    setToast(
                                      "Offer approved. Nothing has been booked or sent.",
                                    );
                                  })
                                }
                              >
                                <Check size={15} />
                                Review & approve
                              </button>
                            ) : (
                              <button
                                className="secondary wide"
                                onClick={() => {
                                  setPrintOffer(off);
                                  setTimeout(() => window.print(), 150);
                                }}
                              >
                                <Download size={15} />
                                Print / save PDF
                              </button>
                            )}
                          </section>
                        ))}
                        {[
                          "OFFER_READY",
                          "WAITING_CUSTOMER",
                          "ON_HOLD",
                          "RESULTS_READY",
                          "SALES_REVIEW",
                        ].includes(current.status) && (
                          <section className="card outcome">
                            <h3>{t("Next step", "مرحله بعدی")}</h3>
                            <select
                              aria-label="Update request status"
                              value=""
                              onChange={(e) => {
                                const state = e.target.value;
                                if (state)
                                  void action(async () => {
                                    await api(
                                      `/requests/${current.id}/transition`,
                                      "POST",
                                      {
                                        state,
                                        reason:
                                          "Agent updated from sales workspace",
                                      },
                                    );
                                    await open(current.id, false);
                                    await load();
                                  });
                              }}
                            >
                              <option value="">Update case status…</option>
                              {(current.status === "ON_HOLD"
                                ? ["SALES_REVIEW", "CANCELLED"]
                                : current.status === "RESULTS_READY"
                                  ? ["SALES_REVIEW", "ON_HOLD", "CANCELLED"]
                                  : current.status === "SALES_REVIEW"
                                    ? ["ON_HOLD", "CANCELLED"]
                                    : [
                                        "WAITING_CUSTOMER",
                                        "WON",
                                        "LOST",
                                        "ON_HOLD",
                                        "CANCELLED",
                                      ]
                              )
                                .filter((s) => s !== current.status)
                                .map((s) => (
                                  <option key={s}>{s}</option>
                                ))}
                            </select>
                            <small>
                              Tracking only. This does not book, pay, or send a
                              message.
                            </small>
                          </section>
                        )}
                      </aside>
                    </div>
                  </>
                )}
              </>
            )}
            {page === "requests" && (
              <section className="card request-list">
                <div className="list-toolbar">
                  <div className="search-input">
                    <Search size={17} />
                    <input
                      aria-label="Filter requests"
                      placeholder={t(
                        "Search customers, routes, statuses…",
                        "جست‌وجوی مشتری، مسیر یا وضعیت…",
                      )}
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </div>
                  <span>{requests.length} requests</span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        {[
                          "Customer / case",
                          "Route",
                          "Travel dates",
                          "Owner",
                          "Status",
                          "Created",
                        ].map((x) => (
                          <th key={x}>{x}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {requests
                        .filter((r) =>
                          [
                            r.customer_name,
                            r.spec.origin,
                            r.spec.destination,
                            r.status,
                          ]
                            .join(" ")
                            .toLowerCase()
                            .includes(query.toLowerCase()),
                        )
                        .map((r) => (
                          <tr
                            key={r.id}
                            onClick={() =>
                              action(async () => {
                                await open(r.id);
                                setPage("desk");
                              })
                            }
                          >
                            <td>
                              <button className="table-link">
                                {r.customer_name}
                              </button>
                              <small>#{r.id.slice(-6).toUpperCase()}</small>
                            </td>
                            <td>
                              {r.spec.origin || "—"} <ArrowRight size={13} />{" "}
                              {r.spec.destination || "—"}
                            </td>
                            <td>
                              {r.spec.departure_date || "To confirm"}
                              <small>
                                {r.spec.adults} adults · {label(r.spec.intent)}
                              </small>
                            </td>
                            <td>{r.owner_name}</td>
                            <td>
                              <Badge value={r.status} />
                            </td>
                            <td>{time(r.created_at)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                {!requests.length && (
                  <div className="empty-results">
                    <Layers3 size={28} />
                    <p>No requests yet. Start a new customer journey.</p>
                  </div>
                )}
              </section>
            )}
            {page === "sources" && (
              <Sources
                sources={sources}
                user={user}
                busy={busy}
                action={action}
                load={load}
                settings={settings}
              />
            )}
            {page === "insights" && (
              <>
                <div className="insight-grid">
                  {[
                    ["Requests handled", metrics.requests],
                    ["Approved offers", metrics.approved_offers],
                    ["Won cases", metrics.won],
                    [
                      "Mean search time",
                      metrics.mean_search_seconds == null
                        ? "—"
                        : metrics.mean_search_seconds + "s",
                    ],
                    [
                      "Completed search success",
                      metrics.search_success_pct == null
                        ? "—"
                        : metrics.search_success_pct + "%",
                    ],
                    ["Demonstration runs", metrics.demo_runs],
                  ].map(([name, val]) => (
                    <div className="card metric-card" key={name}>
                      <span>{name}</span>
                      <strong>{val ?? 0}</strong>
                    </div>
                  ))}
                </div>
                <div className="card insight-note">
                  <BarChart3 size={28} />
                  <h2>Measure value before expanding.</h2>
                  <p>
                    These metrics come from stored requests and search runs.
                    Demonstration runs are included in search metrics and must
                    not be used as evidence of live supplier reliability.
                  </p>
                  <p>
                    Before a live pilot, record your team’s manual time-to-quote
                    baseline and validate at least two flight and two hotel
                    sources.
                  </p>
                </div>
              </>
            )}
            {page === "settings" && (
              <SettingsPage
                user={user}
                settings={settings}
                action={action}
                busy={busy}
                onChange={load}
              />
            )}
          </main>
          <footer className="footer">
            <span>ATLAS / AGENCY COPILOT</span>
            <span>Built for the people behind every journey.</span>
            <span>On-premise · 0.2.1</span>
          </footer>
        </div>
      </div>
      {newModal && (
        <div className="modal-backdrop" onClick={() => setNewModal(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-request-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close new request"
              onClick={() => setNewModal(false)}
            >
              <X />
            </button>
            <span className="eyebrow">NEW JOURNEY</span>
            <h2 id="new-request-title">
              {t(
                "Who are we planning for?",
                "برای چه کسی برنامه‌ریزی می‌کنیم؟",
              )}
            </h2>
            <p>Start a case, then describe the trip or fill in the details.</p>
            <form onSubmit={create}>
              <label>
                Customer / group name
                <input
                  autoFocus
                  required
                  maxLength={100}
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  placeholder="e.g. Sara Ahmadi · Muscat trip"
                />
              </label>
              <button
                className="primary wide"
                disabled={busy || !customer.trim()}
                type="submit"
              >
                Create request <ArrowRight size={17} />
              </button>
            </form>
          </section>
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          <CircleCheck size={19} />
          {toast}
        </div>
      )}
      {printOffer && (
        <div className="print-offer">
          <span className="print-brand">ATLAS · TRAVEL OFFER</span>
          <h1>
            {printOffer.demo
              ? "DEMONSTRATION — NOT BOOKABLE"
              : "Travel proposal"}
          </h1>
          <h2>{printOffer.customer_name}</h2>
          <p>
            Offer #{printOffer.id.slice(-6)} · {time(printOffer.created_at)}
          </p>
          {printOffer.items.map((r: Obj) => (
            <section key={r.id}>
              <h3>{r.title}</h3>
              <p>
                {r.origin && r.origin + " → "}
                {r.destination} · {r.departure_date}{" "}
                {r.return_date && "to " + r.return_date}
              </p>
              <p>
                {r.adults} adults · {r.details}
              </p>
              <p>{r.cancellation_policy}</p>
              <p>
                Rate captured: {time(r.captured_at)} · Valid until:{" "}
                {time(r.expires_at)}
              </p>
            </section>
          ))}
          <h2>Total: {money(printOffer.total, printOffer.currency)}</h2>
          <p>{printOffer.note}</p>
          <p>
            Subject to availability and revalidation. Human-reviewed proposal;
            no booking or payment has been made.
          </p>
          {printOffer.demo && (
            <strong>SYNTHETIC PRICES — FOR PRODUCT DEMONSTRATION ONLY</strong>
          )}
        </div>
      )}
    </>
  );
}
function SpecForm({
  spec,
  setSpec,
  fa = false,
}: {
  spec: Obj;
  setSpec: (s: Obj) => void;
  fa?: boolean;
}) {
  const set = (k: string, v: any) => setSpec({ ...spec, [k]: v });
  return (
    <div className="spec-grid">
      <label className="service-field">
        {fa ? "نوع درخواست" : "Service"}
        <select
          value={spec.intent}
          onChange={(e) => set("intent", e.target.value)}
        >
          <option value="PACKAGE_SEARCH">Flight + Hotel</option>
          <option value="FLIGHT_SEARCH">Flight only</option>
          <option value="HOTEL_SEARCH">Hotel only</option>
        </select>
      </label>
      {spec.intent !== "HOTEL_SEARCH" && (
        <label>
          {fa ? "مبدأ" : "From"}
          <select
            value={spec.origin}
            onChange={(e) => set("origin", e.target.value)}
          >
            <option value="">Select origin</option>
            {Object.entries(airports).map(([code, name]) => (
              <option key={code} value={code}>
                {code} · {name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        {fa ? "مقصد" : "To"}
        <select
          value={spec.destination}
          onChange={(e) => set("destination", e.target.value)}
        >
          <option value="">Select destination</option>
          {Object.entries(airports).map(([code, name]) => (
            <option key={code} value={code}>
              {code} · {name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {fa ? "تاریخ رفت / ورود" : "Departure / check-in"}
        <input
          type="date"
          value={spec.departure_date || ""}
          onChange={(e) => set("departure_date", e.target.value || null)}
        />
      </label>
      <label>
        {fa ? "تاریخ برگشت / خروج" : "Return / check-out"}
        <input
          type="date"
          value={spec.return_date || ""}
          onChange={(e) => set("return_date", e.target.value || null)}
        />
      </label>
      <label>
        {fa ? "بزرگسال" : "Adults"}
        <input
          type="number"
          min={1}
          max={9}
          value={spec.adults}
          onChange={(e) => set("adults", Number(e.target.value))}
        />
      </label>
      {spec.intent !== "FLIGHT_SEARCH" && (
        <>
          <label>
            {fa ? "اتاق" : "Rooms"}
            <input
              type="number"
              min={1}
              max={5}
              value={spec.rooms}
              onChange={(e) => set("rooms", Number(e.target.value))}
            />
          </label>
          <label>
            {fa ? "حداقل ستاره" : "Hotel stars"}
            <select
              value={spec.stars_min}
              onChange={(e) => set("stars_min", Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5].map((x) => (
                <option key={x} value={x}>
                  {x} stars +
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {spec.intent !== "HOTEL_SEARCH" && (
        <>
          <label>
            {fa ? "کلاس پرواز" : "Cabin"}
            <select
              value={spec.cabin}
              onChange={(e) => set("cabin", e.target.value)}
            >
              <option value="ECONOMY">Economy</option>
              <option value="BUSINESS">Business</option>
            </select>
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={spec.direct_only}
              onChange={(e) => set("direct_only", e.target.checked)}
            />
            {fa ? "فقط مستقیم" : "Direct flights only"}
          </label>
        </>
      )}
    </div>
  );
}
function RateCard({
  rate,
  selected,
  best,
  disabled,
  onSelect,
}: {
  rate: Obj;
  selected: boolean;
  best: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  const expired = new Date(rate.expires_at).getTime() <= Date.now();
  return (
    <article className={"rate-card " + (selected ? "selected" : "")}>
      <div className="rate-top">
        <span className="supplier">
          {rate.capture_mode === "MANUAL" && <b>MANUALLY VERIFIED · </b>}
          <i />
          {rate.source_name} <span>v{rate.workflow_version}</span>
        </span>
        {best && (
          <span className="lowest">Lowest shown in {rate.currency}</span>
        )}
      </div>
      <div className="rate-body">
        <div className="rate-logo">
          {rate.kind === "FLIGHT" ? <Plane size={23} /> : <Hotel size={23} />}
        </div>
        <div className="rate-info">
          <h3>{rate.title}</h3>
          {rate.kind === "FLIGHT" ? (
            <div className="route">
              <b>{rate.origin}</b>
              <div>
                <span>
                  {rate.stops === 0 ? "Direct" : rate.stops + " stop(s)"}
                </span>
                <i />
              </div>
              <b>{rate.destination}</b>
            </div>
          ) : (
            <span className="stars">
              {"★".repeat(rate.stars)}{" "}
              <small>{airports[rate.destination]}</small>
            </span>
          )}
          <p>{rate.details}</p>
          <small>
            {rate.departure_date}
            {rate.return_date && " → " + rate.return_date} · {rate.adults}{" "}
            adults
          </small>
        </div>
        <div className="rate-price">
          <strong>{money(rate.net_price, rate.currency)}</strong>
          <span>Total · taxes included</span>
          <button
            className={selected ? "primary" : "secondary"}
            disabled={expired || disabled}
            onClick={onSelect}
          >
            {selected ? (
              <>
                <Check size={14} />
                Selected
              </>
            ) : expired ? (
              "Expired"
            ) : (
              "Select option"
            )}
          </button>
        </div>
      </div>
      <div className="rate-bottom">
        <span>
          <Clock size={12} />
          Captured {time(rate.captured_at)}
        </span>
        <span>
          {expired
            ? "Expired"
            : "Valid until " +
              new Date(rate.expires_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
        </span>
        <details>
          <summary>Rate conditions</summary>
          <p>{rate.cancellation_policy}</p>
        </details>
      </div>
    </article>
  );
}
function Login({ onLogin }: { onLogin: (u: Obj) => void }) {
  const [email, setEmail] = useState("admin@agency.local"),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login-page">
      <div className="login-intro">
        <div className="login-wordmark">
          atlas<span>✦</span>
        </div>
        <span className="eyebrow">TRAVEL AGENCY COPILOT</span>
        <h1>
          Less searching.
          <br />
          More possibilities.
        </h1>
        <p>
          A considered workspace for the people who make every journey happen.
        </p>
        <div className="login-proof">
          <ShieldCheck />
          <span>
            Agency-owned sources.
            <br />
            Human-led decisions.
          </span>
        </div>
        <small>ON-PREMISE / 0.2.1</small>
      </div>
      <div className="login-panel">
        <div className="login-form">
          <span className="eyebrow">WELCOME TO YOUR WORKSPACE</span>
          <h2>Let’s get you signed in.</h2>
          <p>Use the account configured for your agency.</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                onLogin(await api("/auth/login", "POST", { email, password }));
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Email address
              <input
                type="email"
                autoComplete="username"
                value={email}
                required
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                required
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <button className="primary wide" disabled={busy}>
              {busy ? (
                <Loader2 size={17} className="spin" />
              ) : (
                <>
                  Sign in <ArrowRight size={17} />
                </>
              )}
            </button>
          </form>
          <p className="login-help">
            First time here? Your administrator sets the initial password during
            installation. No default password is provided.
          </p>
        </div>
      </div>
    </div>
  );
}
function Sources({
  sources,
  user,
  busy,
  action,
  load,
  settings,
}: {
  sources: Obj[];
  user: Obj;
  busy: boolean;
  action: (fn: () => Promise<void>) => Promise<void>;
  load: () => Promise<void>;
  settings: Obj;
}) {
  const [add, setAdd] = useState(false),
    [edit, setEdit] = useState<Obj | null>(null),
    [form, setForm] = useState({
      name: "",
      kind: "FLIGHT",
      provider: "JSON_API",
      account_ref: "",
      classification: "AGENCY_TAUGHT",
      notes: "",
    }),
    [testSpec, setTestSpec] = useState<Obj>(freshSpec()),
    [mapping, setMapping] = useState(""),
    [versionNote, setVersionNote] = useState(""),
    [result, setResult] = useState<Obj | null>(null);
  return (
    <>
      <div className="source-guide card">
        <div className="guide-step">
          <span>01</span>
          <strong>Connect</strong>
          <small>Add a supplier after installation</small>
        </div>
        <ChevronRight />
        <div className="guide-step">
          <span>02</span>
          <strong>Configure</strong>
          <small>Configure API mapping or manual entry</small>
        </div>
        <ChevronRight />
        <div className="guide-step">
          <span>03</span>
          <strong>Test</strong>
          <small>Pass 3 distinct golden searches</small>
        </div>
        <ChevronRight />
        <div className="guide-step">
          <span>04</span>
          <strong>Activate</strong>
          <small>Admin reviews and enables search</small>
        </div>
      </div>
      <div className="source-toolbar">
        <span>
          {sources.length} sources ·{" "}
          {sources.filter((s) => s.status === "ACTIVE").length} active
        </span>
        {user.role === "ADMIN" && (
          <div>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                action(async () => {
                  await api("/demo/setup", "POST");
                  await load();
                })
              }
            >
              Load demo sources
            </button>
            <button className="primary" onClick={() => setAdd(!add)}>
              <Plus size={16} />
              Add source
            </button>
          </div>
        )}
      </div>
      {!settings.bridge_configured && (
        <div className="info-banner">
          <CircleHelp size={17} />
          Add a Direct JSON API source for automatic searches, or a Supplier
          website for verified manual rates. The custom execution bridge is
          optional.
        </div>
      )}
      {add && (
        <section className="card source-form">
          <h2>Add an agency source</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                const created = await api("/sources", "POST", form);
                setEdit(created);
                setResult(null);
                setTestSpec({
                  ...freshSpec(),
                  intent:
                    created.kind === "FLIGHT"
                      ? "FLIGHT_SEARCH"
                      : "HOTEL_SEARCH",
                });
                await load();
                setAdd(false);
                setForm({ ...form, name: "", account_ref: "", notes: "" });
              });
            }}
          >
            <div className="spec-grid">
              <label>
                Name
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </label>
              <label>
                Service
                <select
                  value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value })}
                >
                  <option>FLIGHT</option>
                  <option>HOTEL</option>
                </select>
              </label>
              <label>
                Execution provider
                <select
                  value={form.provider}
                  onChange={(e) =>
                    setForm({ ...form, provider: e.target.value })
                  }
                >
                  <option value="JSON_API">
                    Direct JSON API — configure in app
                  </option>
                  <option value="MANUAL">
                    Supplier website — verified manual rates
                  </option>
                  <option value="HTTP_BRIDGE">
                    Custom execution bridge (advanced)
                  </option>
                  <option value="DEMO">Demonstration fixture</option>
                </select>
              </label>
              <label>
                Account / browser profile reference
                <input
                  value={form.account_ref}
                  pattern="[a-zA-Z0-9_.-]*"
                  placeholder="agency-supplier-profile"
                  onChange={(e) =>
                    setForm({ ...form, account_ref: e.target.value })
                  }
                />
              </label>
              <label>
                Classification
                <select
                  value={form.classification}
                  onChange={(e) =>
                    setForm({ ...form, classification: e.target.value })
                  }
                >
                  <option>AGENCY_TAUGHT</option>
                  <option>CERTIFIED</option>
                </select>
              </label>
              <label>
                Onboarding notes
                <input
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </label>
            </div>
            <p className="muted">
              Enter references only. Supplier passwords and sessions stay in
              your execution service, never in this form.
            </p>
            <button className="primary" disabled={busy}>
              Create draft source
            </button>
          </form>
        </section>
      )}
      <div className="sources-grid">
        {sources.map((s) => (
          <article className="card source-card" key={s.id}>
            <div className="source-card-top">
              <span className="source-icon">
                {s.kind === "FLIGHT" ? <Plane /> : <Hotel />}
              </span>
              <Badge value={s.status} />
            </div>
            <h3>{s.name}</h3>
            <p>
              {s.provider === "DEMO"
                ? "Demonstration fixture · synthetic results"
                : label(s.classification) + " · authorized integration"}
            </p>
            <div className="source-meta">
              <span>
                {s.kind === "FLIGHT" ? "Flight search" : "Hotel search"}
              </span>
              <span>Workflow v{s.version}</span>
            </div>
            <div className="source-card-bottom">
              <small>
                {
                  s.tests.filter(
                    (x: Obj) => x.success && x.version === s.version,
                  ).length
                }{" "}
                passed test(s)
              </small>
              {user.role === "ADMIN" && (
                <button
                  className="text-button"
                  onClick={() => {
                    setEdit(s);
                    setResult(null);
                    setTestSpec({
                      ...freshSpec(),
                      intent:
                        s.kind === "FLIGHT" ? "FLIGHT_SEARCH" : "HOTEL_SEARCH",
                    });
                  }}
                >
                  Configure <ArrowUpRight size={15} />
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {edit && (
        <div className="modal-backdrop" onClick={() => setEdit(null)}>
          <section
            className="modal source-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="source-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close source"
              onClick={() => setEdit(null)}
            >
              <X />
            </button>
            <span className="eyebrow">ASSISTED SOURCE STUDIO</span>
            <h2 id="source-title">{edit.name}</h2>
            <p>
              Current version {edit.version}. Existing versions remain
              immutable.
            </p>
            <SourceConfigPanel
              key={edit.id}
              source={edit}
              api={api}
              onChange={async (updated) => {
                setEdit(updated);
                await load();
              }}
            />
            {!["JSON_API", "MANUAL"].includes(edit.provider) && (
              <>
                <label>
                  New mapping version
                  <input
                    value={mapping}
                    placeholder="supplier-flight-v2"
                    onChange={(e) => setMapping(e.target.value)}
                  />
                </label>
                <label>
                  Change notes
                  <input
                    value={versionNote}
                    onChange={(e) => setVersionNote(e.target.value)}
                  />
                </label>
                <button
                  className="secondary"
                  disabled={busy || !mapping}
                  onClick={() =>
                    action(async () => {
                      const s = await api(
                        "/sources/" + edit.id + "/versions",
                        "POST",
                        { mapping_version: mapping, notes: versionNote },
                      );
                      setEdit(s);
                      setMapping("");
                      await load();
                    })
                  }
                >
                  Save new draft version
                </button>
              </>
            )}
            {edit.provider !== "MANUAL" && (
              <>
                <hr />
                <h3>Golden search test</h3>
                <SpecForm spec={testSpec} setSpec={setTestSpec} />
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      const r = await api(
                        "/sources/" + edit.id + "/test",
                        "POST",
                        {
                          spec: testSpec,
                        },
                      );
                      setResult(r);
                      const ss = await api("/sources");
                      setEdit(ss.find((s: Obj) => s.id === edit.id));
                      await load();
                    })
                  }
                >
                  {busy ? (
                    <Loader2 size={15} className="spin" />
                  ) : (
                    <Play size={15} />
                  )}
                  Run golden test
                </button>
                {result && (
                  <div className={result.success ? "info-banner" : "error"}>
                    {result.success ? "Test passed" : result.error_code} ·{" "}
                    {result.duration_ms} ms
                  </div>
                )}
                <p className="muted">
                  Activation requires three distinct successful specifications
                  for the current version. Change route, dates, or passenger
                  count between tests. The latest test must pass.
                </p>
                <div className="modal-actions">
                  <button
                    className="danger-button"
                    disabled={busy}
                    onClick={() =>
                      action(async () => {
                        setEdit(
                          await api("/sources/" + edit.id + "/disable", "POST"),
                        );
                        await load();
                      })
                    }
                  >
                    Disable source
                  </button>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      action(async () => {
                        setEdit(
                          await api(
                            "/sources/" + edit.id + "/activate",
                            "POST",
                          ),
                        );
                        await load();
                      })
                    }
                  >
                    <Check size={16} />
                    Approve & activate
                  </button>
                </div>
              </>
            )}
            {edit.provider === "MANUAL" && (
              <button
                className="danger-button"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    setEdit(
                      await api("/sources/" + edit.id + "/disable", "POST"),
                    );
                    await load();
                  })
                }
              >
                Disable supplier
              </button>
            )}
            <details>
              <summary>Version and test history</summary>
              {edit.versions.map((v: Obj) => (
                <p key={v.version}>
                  v{v.version} · {v.mapping_version} · {v.notes}
                </p>
              ))}
              {edit.tests.slice(-10).map((x: Obj) => (
                <p key={x.id}>
                  {x.success ? "PASS" : "FAIL"} · v{x.version} · {x.spec.origin}{" "}
                  → {x.spec.destination} · {x.spec.departure_date}
                </p>
              ))}
            </details>
          </section>
        </div>
      )}
    </>
  );
}
function SettingsPage({
  user,
  settings,
  action,
  busy,
  onChange,
}: {
  user: Obj;
  settings: Obj;
  action: (fn: () => Promise<void>) => Promise<void>;
  busy: boolean;
  onChange: () => Promise<void>;
}) {
  const [users, setUsers] = useState<Obj[]>([]),
    [form, setForm] = useState({
      name: "",
      email: "",
      password: "",
      role: "AGENT",
    });
  useEffect(() => {
    if (user.role === "ADMIN")
      api("/users")
        .then(setUsers)
        .catch(() => {});
  }, []);
  return (
    <div className="settings-grid">
      {user.role === "ADMIN" && (
        <AISettingsPanel api={api} onChange={onChange} />
      )}
      <section className="card setting-card">
        <h2>Integration status</h2>
        {[
          ["Understanding", settings.ai_provider],
          [
            "Voice transcription",
            settings.voice_enabled
              ? "Configured · sends audio to Gemini"
              : "Needs Gemini configuration",
          ],
          [
            "Optional custom bridge",
            settings.bridge_configured
              ? "Bridge configured · verify with golden tests"
              : "Not connected",
          ],
          ["Deployment", "Single agency · SQLite · one API worker"],
        ].map(([k, v]) => (
          <div className="setting-row" key={k}>
            <span>{k}</span>
            <strong>{v}</strong>
          </div>
        ))}
        <p>
          Gemini receives request text or audio when enabled. Raw audio is not
          saved. Administrators manage the Gemini key and model in the AI
          settings form above.
        </p>
        <p>
          Supplier logins, OTP, and CAPTCHA are handled manually in the
          execution service. No booking, cancellation, or payment action is
          implemented.
        </p>
        {user.role === "ADMIN" && (
          <button
            className="secondary"
            onClick={() =>
              action(async () => {
                const data = await api("/diagnostics");
                const url = URL.createObjectURL(
                  new Blob([JSON.stringify(data, null, 2)], {
                    type: "application/json",
                  }),
                );
                const a = document.createElement("a");
                a.href = url;
                a.download = "atlas-diagnostics.json";
                a.click();
                URL.revokeObjectURL(url);
              })
            }
          >
            <Download size={16} />
            Export sanitized diagnostics
          </button>
        )}
      </section>
      <section className="card setting-card">
        <h2>Live pilot checklist</h2>
        <ol className="checklist">
          <li>Choose two authorized flight and two hotel suppliers.</li>
          <li>Choose a direct API source or a manual supplier website.</li>
          <li>
            Save and validate the supplier response mapping in Source Studio.
          </li>
          <li>
            Configure the supplier API, test three golden searches, then
            activate. Use manual entry for website-only suppliers.
          </li>
          <li>
            Run manual rate comparisons and a restart / backup restore test.
          </li>
          <li>Record team time-to-quote before and during the pilot.</li>
        </ol>
        <p>
          The full source package includes installation instructions, API
          contracts, tests, backup tooling, and the implementation gap register.
        </p>
      </section>
      {user.role === "ADMIN" && (
        <section className="card setting-card team-settings">
          <h2>
            <Users size={20} /> Team access
          </h2>
          <div className="team-list">
            {users.map((u) => (
              <div key={u.id}>
                <span className="avatar small">{u.name.slice(0, 1)}</span>
                <strong>
                  {u.name}
                  <small>{u.email}</small>
                </strong>
                <Badge value={u.role} />
              </div>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                await api("/users", "POST", form);
                setUsers(await api("/users"));
                setForm({ name: "", email: "", password: "", role: "AGENT" });
              });
            }}
          >
            <div className="spec-grid">
              <label>
                Name
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </label>
              <label>
                Initial password
                <input
                  type="password"
                  required
                  minLength={12}
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(e) =>
                    setForm({ ...form, password: e.target.value })
                  }
                />
              </label>
              <label>
                Role
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                >
                  <option>AGENT</option>
                  <option>MANAGER</option>
                  <option>ADMIN</option>
                </select>
              </label>
            </div>
            <button className="primary" disabled={busy}>
              <Plus size={16} />
              Add team member
            </button>
          </form>
        </section>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
