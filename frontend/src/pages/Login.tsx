import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Cloud, Eye, EyeOff, Lock, Mail, AlertCircle, Loader2, Shield, Zap, Globe } from "lucide-react";
import { useAuth } from "@/stores/auth";

export function Login(): JSX.Element {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const login = useAuth((s) => s.login);

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
    }, 800);
  };

  return (
    <div className="flex min-h-screen bg-[#0a0e1a]">
      {/* Left Panel - Branding */}
      <div className="hidden relative overflow-hidden lg:flex lg:w-[55%] flex-col justify-between bg-gradient-to-br from-[#0c1829] via-[#0f1f3d] to-[#0a1628] p-12">
        {/* Background Effects */}
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 -left-40 h-[600px] w-[600px] rounded-full bg-cyan-500/5 blur-[120px]" />
          <div className="absolute bottom-0 right-0 h-[400px] w-[400px] rounded-full bg-blue-500/5 blur-[100px]" />
          {/* Grid pattern */}
          <div className="absolute inset-0 opacity-[0.03]" style={{
            backgroundImage: "linear-gradient(rgba(6,182,212,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.5) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }} />
        </div>

        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/20">
              <Cloud className="h-7 w-7 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">AERO-TRACK</h1>
              <p className="text-xs text-cyan-400/70 font-mono">EWAI Decision Support</p>
            </div>
          </div>
        </div>

        <div className="relative z-10 space-y-10">
          <div>
            <h2 className="text-4xl font-bold leading-tight text-white">
              Extreme Weather<br />
              <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">Intelligence Platform</span>
            </h2>
            <p className="mt-4 max-w-lg text-sm leading-relaxed text-slate-400">
              Spatio-temporal tracking of extreme weather anomalies with AI-powered downscaling,
              uncertainty quantification, and decision-support alerts. Research prototype for PS 26078 (MoES / NCMRWF).
            </p>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {[
              { icon: Shield, title: "Honest Science", desc: "Baselines beaten before promotion" },
              { icon: Zap, title: "Real-time Pipeline", desc: "ERA5 → Detection → Tracking → Alert" },
              { icon: Globe, title: "India Domain Focus", desc: "68°E–98°E, 5°N–30°N coverage" },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4 backdrop-blur-sm">
                <Icon className="mb-2 h-5 w-5 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">{title}</h3>
                <p className="mt-1 text-xs text-slate-400">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 text-xs text-slate-500">
          <p>PS 26078 · MoES / NCMRWF · Research prototype</p>
          <p className="mt-1">Not an official warning service. Consult IMD and State/District Disaster Management Authorities.</p>
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-16">
        <div className="w-full max-w-md space-y-8">
          {/* Mobile Logo */}
          <div className="flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/20">
              <Cloud className="h-6 w-6 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">AERO-TRACK</h1>
              <p className="text-[10px] text-cyan-400/70 font-mono">EWAI Decision Support</p>
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-bold text-white">Sign in to your account</h2>
            <p className="mt-2 text-sm text-slate-400">
              Access the extreme weather intelligence dashboard
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1.5">
                Email address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@ewai.gov.in"
                  required
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/30"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                  className="w-full rounded-lg border border-slate-700 bg-slate-800/50 py-2.5 pl-10 pr-10 text-sm text-white placeholder-slate-500 outline-none transition focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/30"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 transition hover:from-cyan-400 hover:to-blue-400 hover:shadow-cyan-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Signing in...
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>

          <div className="space-y-3">
            <div className="relative">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-700/50" /></div>
              <div className="relative flex justify-center text-xs"><span className="bg-[#0a0e1a] px-3 text-slate-500">Demo credentials</span></div>
            </div>

            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 space-y-2">
              <p className="text-xs text-slate-400 font-medium">Available accounts:</p>
              {[
                { email: "admin@ewai.gov.in", password: "admin", role: "Full access" },
                { email: "analyst@ewai.gov.in", password: "analyst", role: "Analyst" },
                { email: "viewer@ewai.gov.in", password: "viewer", role: "Read-only" },
              ].map((acc) => (
                <button
                  key={acc.email}
                  type="button"
                  onClick={() => { setEmail(acc.email); setPassword(acc.password); setError(""); }}
                  className="flex w-full items-center justify-between rounded-md border border-slate-700/30 bg-slate-800/50 px-3 py-2 text-left transition hover:border-cyan-500/30 hover:bg-slate-800"
                >
                  <div>
                    <span className="text-xs font-mono text-slate-300">{acc.email}</span>
                    <span className="ml-2 text-[10px] text-slate-500">/ {acc.password}</span>
                  </div>
                  <span className="text-[10px] text-slate-500">{acc.role}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
