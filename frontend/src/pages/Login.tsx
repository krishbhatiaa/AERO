import { useState, useRef, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Cloud,
  Eye,
  EyeOff,
  Lock,
  Mail,
  AlertCircle,
  Loader2,
  Shield,
  Zap,
  Globe,
  Sun,
  Moon,
  Accessibility,
  Type,
} from "lucide-react";
import { useAuth } from "@/stores/auth";
import { useUi } from "@/stores/ui";
import Language from "@/components/Language";

/* ─── tiny toggle-switch ─────────────────────────────────────────────────── */
function Toggle({
  checked,
  onChange,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  id: string;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      id={id}
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]/60 ${
        checked
          ? "border-[#2563EB] bg-[#2563EB]"
          : "border-[#CBD5E1] bg-[#F1F5F9] dark:border-[#334155] dark:bg-[#1E293B]"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
          checked ? "translate-x-[14px]" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

/* ─── Accessibility Popover ──────────────────────────────────────────────── */
function A11yPopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const textSize    = useUi((s) => s.textSize);
  const reduceMotion = useUi((s) => s.reduceMotion);
  const highContrast = useUi((s) => s.highContrast);
  const setTextSize    = useUi((s) => s.setTextSize);
  const setReduceMotion = useUi((s) => s.setReduceMotion);
  const setHighContrast = useUi((s) => s.setHighContrast);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="Accessibility settings"
        className="flex items-center gap-1.5 rounded-lg border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#111827] px-2.5 py-1.5 text-xs font-medium text-[#475569] dark:text-[#94A3B8] hover:text-[#0F172A] dark:hover:text-[#F8FAFC] transition-colors shadow-[0_1px_2px_0_rgb(0,0,0,0.05)]"
      >
        <Accessibility className="h-3.5 w-3.5" />
        <span className="hidden sm:block font-mono text-[11px]">A11y</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Accessibility settings"
          className="absolute right-0 top-9 z-50 w-56 rounded-xl border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#111827] shadow-lg p-4 space-y-4"
        >
          {/* Text size */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Type className="h-3.5 w-3.5 text-[#64748B]" />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748B] dark:text-[#94A3B8]">
                Text size
              </span>
            </div>
            <div className="flex gap-1.5">
              {(["sm", "md", "lg"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setTextSize(s)}
                  className={`flex-1 rounded-md border py-1 text-[11px] font-medium transition-colors ${
                    textSize === s
                      ? "border-[#2563EB] bg-[#EFF6FF] text-[#1D4ED8] dark:border-[#3B82F6] dark:bg-[#1E3A8A]/40 dark:text-[#60A5FA]"
                      : "border-[#E2E8F0] dark:border-[#334155] text-[#64748B] dark:text-[#94A3B8] hover:border-[#CBD5E1] dark:hover:border-[#475569]"
                  }`}
                >
                  {s === "sm" ? "Small" : s === "md" ? "Medium" : "Large"}
                </button>
              ))}
            </div>
          </div>

          {/* Reduce motion */}
          <div className="flex items-center justify-between">
            <label htmlFor="a11y-motion" className="text-xs text-[#334155] dark:text-[#CBD5E1] cursor-pointer">
              Reduce motion
            </label>
            <Toggle checked={reduceMotion} onChange={setReduceMotion} id="a11y-motion" />
          </div>

          {/* High contrast */}
          <div className="flex items-center justify-between">
            <label htmlFor="a11y-contrast" className="text-xs text-[#334155] dark:text-[#CBD5E1] cursor-pointer">
              High contrast
            </label>
            <Toggle checked={highContrast} onChange={setHighContrast} id="a11y-contrast" />
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Login Page ─────────────────────────────────────────────────────────── */
export function Login(): JSX.Element {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const login    = useAuth((s) => s.login);
  const theme    = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    setTimeout(() => {
      const success = login(email, password);
      if (success) {
        navigate("/", { replace: true });
      } else {
        setError("Invalid email or password. Try admin@ewai.gov.in / admin");
      }
      setLoading(false);
    }, 600);
  };

  const FEATURE_CARDS = [
    { icon: Shield, title: "HONEST SCIENCE",       desc: "Baselines beaten before promotion" },
    { icon: Zap,    title: "REAL-TIME PIPELINE",   desc: "NWP → Detection → Tracking → Alert" },
    { icon: Globe,  title: "INDIA DOMAIN FOCUS",   desc: "68°E–98°E, 5°N–30°N coverage" },
  ];

  const DEMO_ACCOUNTS = [
    { email: "admin@ewai.gov.in",   password: "admin",   role: "Full access", badge: "bg-[#DCFCE7] text-[#15803D] border-[#BBF7D0] dark:bg-[#14532D]/30 dark:text-[#4ADE80] dark:border-[#166534]" },
    { email: "analyst@ewai.gov.in", password: "analyst", role: "Analyst",     badge: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE] dark:bg-[#1E3A8A]/30 dark:text-[#60A5FA] dark:border-[#1E40AF]" },
    { email: "viewer@ewai.gov.in",  password: "viewer",  role: "Read-only",   badge: "bg-[#F1F5F9] text-[#475569] border-[#E2E8F0] dark:bg-[#1E293B] dark:text-[#94A3B8] dark:border-[#334155]" },
  ];

  return (
    <div className="relative flex min-h-screen w-full bg-[#FFFFFF] dark:bg-[#0B1120] text-[#0F172A] dark:text-[#F8FAFC] transition-colors">

      {/* ── Top-right controls ───────────────────────────────────────────── */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
        <A11yPopover />
        <Language />

        {/* Theme toggle */}
        <button
          type="button"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex items-center gap-1.5 rounded-lg border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#111827] px-2.5 py-1.5 text-xs font-medium text-[#475569] dark:text-[#94A3B8] hover:text-[#0F172A] dark:hover:text-[#F8FAFC] transition-colors shadow-[0_1px_2px_0_rgb(0,0,0,0.05)]"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? (
            <Sun className="h-3.5 w-3.5 text-[#F59E0B]" />
          ) : (
            <Moon className="h-3.5 w-3.5 text-[#64748B]" />
          )}
          <span className="hidden sm:block font-mono text-[11px]">
            {theme === "dark" ? "Light" : "Dark"}
          </span>
        </button>
      </div>

      {/* ── LEFT PANEL ──────────────────────────────────────────────────── */}
      <div className="hidden relative overflow-hidden lg:flex lg:w-[54%] flex-col justify-between bg-[#FFFFFF] dark:bg-[#0B1120] border-r border-[#E5E7EB] dark:border-[#1E293B] p-12 xl:p-16">
        {/* Subtle scientific background */}
        <div className="absolute inset-0 pointer-events-none select-none overflow-hidden" aria-hidden="true">
          <div
            className="absolute inset-0 opacity-[0.035] dark:opacity-[0.05]"
            style={{
              backgroundImage: "radial-gradient(#2563EB 1px, transparent 1px)",
              backgroundSize: "28px 28px",
            }}
          />
          <svg
            className="absolute -right-20 top-1/4 h-[550px] w-[550px] text-[#2563EB]/[0.04] dark:text-[#3B82F6]/[0.05]"
            viewBox="0 0 400 400"
            fill="none"
            stroke="currentColor"
          >
            <circle cx="200" cy="200" r="80"  strokeWidth="1"   strokeDasharray="3 3" />
            <circle cx="200" cy="200" r="140" strokeWidth="1" />
            <circle cx="200" cy="200" r="195" strokeWidth="0.8" strokeDasharray="4 4" />
            <line x1="200" y1="0"   x2="200" y2="400" strokeWidth="0.8" strokeDasharray="2 4" />
            <line x1="0"   y1="200" x2="400" y2="200" strokeWidth="0.8" strokeDasharray="2 4" />
          </svg>
          <div className="absolute -top-32 -left-32 h-[420px] w-[420px] rounded-full bg-[#2563EB]/[0.03] dark:bg-[#3B82F6]/[0.03] blur-[100px]" />
        </div>

        {/* Branding */}
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#111827] text-[#2563EB] dark:text-[#3B82F6] shadow-[0_1px_2px_0_rgb(0,0,0,0.05)]">
              <Cloud className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-[20px] font-bold text-[#0F172A] dark:text-[#F8FAFC] tracking-tight leading-none">
                AERO-TRACK
              </h1>
              <p className="mt-1 font-mono text-xs font-medium text-[#2563EB] dark:text-[#3B82F6] tracking-wide">
                EWAI Decision Support
              </p>
            </div>
          </div>
        </div>

        {/* Hero content */}
        <div className="relative z-10 my-auto py-8 space-y-7 max-w-[620px]">
          {/* Research badge */}
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[#2563EB]/25 bg-white dark:bg-[#111827] px-3 py-1 text-xs font-mono font-medium text-[#2563EB] dark:text-[#3B82F6] shadow-[0_1px_2px_0_rgb(0,0,0,0.05)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#2563EB] dark:bg-[#3B82F6] animate-pulseDot" />
              PS 26078 · MoES / NCMRWF Research Prototype
            </div>
          </div>

          {/* Headline */}
          <div className="space-y-3">
            <h2 className="text-4xl xl:text-[44px] font-bold tracking-tight text-[#0F172A] dark:text-[#F8FAFC] leading-[1.08]">
              Extreme Weather
              <br />
              <span className="text-[#2563EB] dark:text-[#3B82F6]">Intelligence Platform</span>
            </h2>
            <p className="text-sm xl:text-[15px] leading-relaxed text-[#475569] dark:text-[#94A3B8]">
              Spatio-temporal tracking of extreme weather anomalies with AI-powered downscaling,
              uncertainty quantification, and decision-support alerts.
            </p>
            <p className="font-mono text-xs text-[#64748B]">
              Research prototype for PS 26078 · MoES / NCMRWF
            </p>
          </div>

          {/* Feature cards */}
          <div className="grid grid-cols-3 gap-3.5 pt-2">
            {FEATURE_CARDS.map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-xl border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#111827] p-4 shadow-[0_1px_2px_0_rgb(0,0,0,0.04)] hover:border-[#93C5FD] dark:hover:border-[#3B82F6]/50 transition-colors"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#EFF6FF] dark:bg-[#1E293B] text-[#2563EB] dark:text-[#3B82F6] mb-3">
                  <Icon className="h-4 w-4" />
                </div>
                <h3 className="text-[11px] font-bold text-[#0F172A] dark:text-[#F8FAFC] tracking-wider uppercase">
                  {title}
                </h3>
                <p className="mt-1 text-[11px] leading-snug text-[#64748B] dark:text-[#94A3B8]">
                  {desc}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer disclaimer */}
        <div className="relative z-10 text-[11px] text-[#94A3B8] dark:text-[#64748B] space-y-0.5 pt-4">
          <p className="font-medium">PS 26078 · MoES / NCMRWF · Research prototype</p>
          <p>Not an official warning service. Consult IMD and State/District Disaster Management Authorities.</p>
        </div>
      </div>

      {/* ── RIGHT PANEL: Login form ──────────────────────────────────────── */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-14 xl:px-20 bg-[#FFFFFF] dark:bg-[#0B1120]">
        <div className="w-full max-w-[430px] space-y-6">

          {/* Mobile branding */}
          <div className="lg:hidden flex flex-col gap-3 mb-2">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#111827] text-[#2563EB] dark:text-[#3B82F6]">
                <Cloud className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-base font-bold text-[#0F172A] dark:text-[#F8FAFC]">AERO-TRACK</h1>
                <p className="font-mono text-[10px] text-[#2563EB] dark:text-[#3B82F6]">EWAI Decision Support</p>
              </div>
            </div>
            <div className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#2563EB]/25 bg-white dark:bg-[#111827] px-2.5 py-0.5 font-mono text-[10px] text-[#2563EB] dark:text-[#3B82F6]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#2563EB]" />
              PS 26078 · MoES / NCMRWF
            </div>
          </div>

          {/* Heading */}
          <div>
            <h2 className="text-[28px] lg:text-[30px] font-bold text-[#0F172A] dark:text-[#F8FAFC] tracking-tight leading-tight">
              Sign in to your account
            </h2>
            <p className="mt-1.5 text-sm text-[#64748B] dark:text-[#94A3B8]">
              Access the extreme weather intelligence dashboard
            </p>
          </div>

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {error && (
              <div
                role="alert"
                aria-live="assertive"
                className="flex items-center gap-2.5 rounded-[10px] border border-[#FECACA] bg-[#FEF2F2] px-3.5 py-2.5 text-xs font-medium text-[#B91C1C] dark:bg-[#450A0A]/30 dark:border-[#991B1B]/50 dark:text-[#FCA5A5] shadow-[0_1px_2px_0_rgb(0,0,0,0.05)]"
              >
                <AlertCircle className="h-4 w-4 shrink-0 text-[#DC2626] dark:text-[#F87171]" />
                <span>{error}</span>
              </div>
            )}

            {/* Email */}
            <div>
              <label htmlFor="login-email" className="block text-xs font-medium text-[#334155] dark:text-[#CBD5E1] mb-1.5">
                Email address
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" aria-hidden="true" />
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@ewai.gov.in"
                  required
                  autoComplete="email"
                  aria-required="true"
                  className="h-12 w-full rounded-[10px] border border-[#CBD5E1] dark:border-[#334155] bg-[#F8FAFC] dark:bg-[#0B1120] py-2.5 pl-10 pr-4 text-sm text-[#0F172A] dark:text-[#F8FAFC] placeholder-[#94A3B8] outline-none transition focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/10"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label htmlFor="login-password" className="block text-xs font-medium text-[#334155] dark:text-[#CBD5E1] mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94A3B8]" aria-hidden="true" />
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                  autoComplete="current-password"
                  aria-required="true"
                  className="h-12 w-full rounded-[10px] border border-[#CBD5E1] dark:border-[#334155] bg-[#F8FAFC] dark:bg-[#0B1120] py-2.5 pl-10 pr-11 text-sm text-[#0F172A] dark:text-[#F8FAFC] placeholder-[#94A3B8] outline-none transition focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#94A3B8] hover:text-[#475569] dark:hover:text-[#CBD5E1] transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              id="login-submit"
              type="submit"
              disabled={loading}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-[#2563EB] hover:bg-[#1D4ED8] active:bg-[#1E40AF] text-sm font-medium text-white shadow-[0_1px_3px_0_rgb(0,0,0,0.15)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  <span>Signing in…</span>
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>

          {/* Demo credentials */}
          <div className="space-y-3 pt-2">
            <div className="relative">
              <div className="absolute inset-0 flex items-center" aria-hidden="true">
                <div className="w-full border-t border-[#E2E8F0] dark:border-[#1E293B]" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-[#FFFFFF] dark:bg-[#0B1120] px-3 font-mono text-[11px] font-semibold text-[#94A3B8] uppercase tracking-wider">
                  DEMO CREDENTIALS
                </span>
              </div>
            </div>

            <p className="text-[10px] font-semibold text-[#64748B] dark:text-[#94A3B8] uppercase tracking-wider">
              CLICK AN ACCOUNT TO AUTOFILL:
            </p>

            <div className="space-y-2" role="group" aria-label="Demo credentials">
              {DEMO_ACCOUNTS.map((acc) => (
                <button
                  key={acc.email}
                  type="button"
                  onClick={() => { setEmail(acc.email); setPassword(acc.password); setError(""); }}
                  className="flex h-[48px] w-full items-center justify-between rounded-[10px] border border-[#E2E8F0] dark:border-[#1E293B] bg-white dark:bg-[#0B1120] px-3.5 text-left hover:border-[#93C5FD] dark:hover:border-[#3B82F6]/50 hover:bg-[#F8FAFC] dark:hover:bg-[#111827] transition-all shadow-[0_1px_2px_0_rgb(0,0,0,0.04)] group"
                  aria-label={`${acc.role}: ${acc.email}`}
                >
                  <div className="flex items-center">
                    <span className="font-mono text-xs font-medium text-[#0F172A] dark:text-[#F8FAFC] group-hover:text-[#2563EB] dark:group-hover:text-[#3B82F6] transition-colors">
                      {acc.email}
                    </span>
                    <span className="ml-1.5 font-mono text-[11px] text-[#94A3B8]">/ {acc.password}</span>
                  </div>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${acc.badge}`}>
                    {acc.role}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
