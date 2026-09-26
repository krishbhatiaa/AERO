import * as Tooltip from "@radix-ui/react-tooltip";
import {
  Activity, AlertTriangle, BarChart3, Calendar, Cloud, Database, Globe,
  LayoutDashboard, LogOut, Menu, Moon, Settings, Shield, Sun, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useHealth } from "@/hooks/queries";
import { useLive, useLiveConnection } from "@/hooks/live";
import { useAuth } from "@/stores/auth";
import { useUi } from "@/stores/ui";
import { cn } from "@/lib/utils";
import Language from "@/components/Language";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/events", label: "Events", icon: Calendar },
  { to: "/alerts", label: "Alerts", icon: AlertTriangle },
  { to: "/globe", label: "3D Globe", icon: Globe },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/models", label: "Models", icon: Shield },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/system", label: "System", icon: Settings },
];

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  analyst: "bg-blue-500/10 text-blue-600 dark:text-cyan-400 border-blue-500/20",
  viewer: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
};

function UserAvatar({ name, role }: { name: string; role: string }): JSX.Element {
  const initials = name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold border", ROLE_COLORS[role] || ROLE_COLORS.viewer)}>
      {initials}
    </div>
  );
}

export function Shell(): JSX.Element {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const navigate = useNavigate();
  const loc = useLocation();
  const health = useHealth();
  const ws = useLive((s) => s.status);
  useLiveConnection();

  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);

  const online = health.status === "success";

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  // Close mobile sidebar on route change
  useEffect(() => { setMobileOpen(false); }, [loc.pathname]);

  return (
    <Tooltip.Provider delayDuration={200}>
      <div className="flex h-screen overflow-hidden bg-background text-on-surface">
        {/* Sidebar */}
        <aside className={cn(
          "flex flex-col border-r border-outline-variant/40 bg-surface-container-lowest transition-all duration-300",
          sidebarOpen ? "w-60" : "w-[68px]",
          "hidden lg:flex",
        )}>
          {/* Logo */}
          <div className="flex h-14 items-center gap-3 border-b border-outline-variant/40 px-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Cloud className="h-5 w-5 text-primary" />
            </div>
            {sidebarOpen && (
              <div className="min-w-0">
                <div className="text-sm font-bold text-on-surface truncate">AERO-TRACK</div>
                <div className="text-[10px] font-mono text-on-surface-variant">EWAI v0.1</div>
              </div>
            )}
          </div>

          {/* Navigation */}
          <div className="flex-1 overflow-y-auto px-2 py-2">
            {sidebarOpen && (
              <div className="px-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
                Navigation
              </div>
            )}
            <nav className="space-y-1" aria-label="Main navigation">
              {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) => cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                    isActive
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
                  )}
                >
                  <Icon className="h-4.5 w-4.5 shrink-0" />
                  {sidebarOpen && <span className="truncate">{label}</span>}
                </NavLink>
              ))}
            </nav>
          </div>

          {/* Multilingual Selector in Sidebar */}
          <div className="border-t border-outline-variant/40 p-2">
            {sidebarOpen ? (
              <div className="space-y-1">
                <div className="px-1 text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
                  Language
                </div>
                <Language direction="up" fullWidth />
              </div>
            ) : (
              <div className="flex justify-center" title="Select Language">
                <Language direction="up" />
              </div>
            )}
          </div>

          {/* User / Login Section */}
          <div className="border-t border-outline-variant/40 p-3">
            {user ? (
              sidebarOpen ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2.5">
                    <UserAvatar name={user.name} role={user.role} />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold text-on-surface truncate">{user.name}</div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-on-surface-variant capitalize">{user.role}</span>
                        <span className="inline-block rounded bg-amber-500/15 px-1 py-0.2 text-[9px] font-mono font-medium text-amber-600 dark:text-amber-400">
                          Demo
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={handleLogout}
                      className="rounded-md p-1.5 text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition"
                      title="Sign out"
                    >
                      <LogOut className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="flex items-center justify-between rounded-md bg-surface-container-low px-2 py-1 text-[10px] text-on-surface-variant">
                    <span>Auth status</span>
                    <span className="font-mono text-amber-600 dark:text-amber-400 font-medium">Login Disabled (Demo)</span>
                  </div>
                </div>
              ) : (
                <button
                  onClick={handleLogout}
                  className="flex w-full justify-center rounded-md p-2 text-on-surface-variant hover:bg-surface-container"
                  title="Sign out"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              )
            ) : (
              sidebarOpen ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-on-surface-variant">
                    <span>Guest Session</span>
                    <span className="rounded bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] text-amber-500">Demo Active</span>
                  </div>
                  <NavLink
                    to="/login"
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2 text-xs font-semibold text-on-primary shadow-xs hover:bg-primary/90 transition"
                  >
                    <span>Login</span>
                  </NavLink>
                </div>
              ) : (
                <NavLink to="/login" className="flex w-full justify-center rounded-md p-2 text-primary" title="Login">
                  <LogOut className="h-4 w-4 rotate-180" />
                </NavLink>
              )
            )}
          </div>
        </aside>

        {/* Mobile Sidebar Overlay */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-xs" onClick={() => setMobileOpen(false)} />
            <aside className="absolute left-0 top-0 h-full w-64 bg-surface-container-lowest border-r border-outline-variant/40 shadow-2xl flex flex-col">
              <div className="flex h-14 items-center justify-between border-b border-outline-variant/40 px-4">
                <div className="flex items-center gap-2">
                  <Cloud className="h-5 w-5 text-primary" />
                  <span className="text-sm font-bold text-on-surface">AERO-TRACK</span>
                </div>
                <button onClick={() => setMobileOpen(false)} className="rounded-lg p-1.5 hover:bg-surface-container text-on-surface-variant">
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-2">
                <div className="px-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
                  Navigation
                </div>
                <nav className="space-y-1">
                  {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
                    <NavLink
                      key={to}
                      to={to}
                      end={end}
                      className={({ isActive }) => cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                        isActive ? "bg-primary/10 text-primary font-semibold" : "text-on-surface-variant hover:bg-surface-container",
                      )}
                    >
                      <Icon className="h-4.5 w-4.5 shrink-0" />
                      <span>{label}</span>
                    </NavLink>
                  ))}
                </nav>
              </div>

              {/* Mobile Multilingual Selector */}
              <div className="border-t border-outline-variant/40 p-3">
                <div className="px-1 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
                  Language
                </div>
                <Language direction="up" fullWidth />
              </div>

              {/* Mobile User Section */}
              <div className="border-t border-outline-variant/40 p-3 bg-surface-container-low/50">
                {user ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <UserAvatar name={user.name} role={user.role} />
                        <div>
                          <div className="text-xs font-semibold text-on-surface">{user.name}</div>
                          <div className="text-[10px] text-on-surface-variant capitalize">{user.role} · Demo</div>
                        </div>
                      </div>
                      <button
                        onClick={handleLogout}
                        className="rounded-lg p-1.5 text-on-surface-variant hover:bg-surface-container"
                        title="Sign out"
                      >
                        <LogOut className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ) : (
                  <NavLink
                    to="/login"
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2 text-xs font-semibold text-on-primary shadow-xs"
                  >
                    <span>Login</span>
                  </NavLink>
                )}
              </div>
            </aside>
          </div>
        )}

        {/* Main Content */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Top Bar */}
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-outline-variant/40 bg-surface-container-lowest px-4">
            <div className="flex items-center gap-3">
              <button onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-on-surface-variant hover:bg-surface-container lg:hidden">
                <Menu className="h-5 w-5" />
              </button>
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="hidden rounded-lg p-2 text-on-surface-variant hover:bg-surface-container lg:block"
                title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
              >
                <Menu className="h-4 w-4" />
              </button>
              <div className="hidden items-center gap-2 text-xs text-on-surface-variant md:flex">
                <span className="font-mono">SOURCE</span>
                <span className="rounded bg-surface-container px-1.5 py-0.5 font-mono text-[10px]">{health.data?.mode?.data_kind_in_use || "SYNTHETIC_DEMO"}</span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Status Indicators */}
              <div className="hidden items-center gap-4 text-xs text-on-surface-variant sm:flex">
                <div className="flex items-center gap-1.5">
                  <div className={cn("h-2 w-2 rounded-full", online ? "bg-emerald-500 animate-pulse" : "bg-red-500")} />
                  <span className="font-mono text-[10px]">{online ? "ONLINE" : "OFFLINE"}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Activity className="h-3 w-3" />
                  <span className="font-mono text-[10px]">LIVE {ws === "open" ? "ON" : "OFF"}</span>
                </div>
              </div>

              {/* Theme Toggle */}
              <button
                type="button"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="flex items-center justify-center rounded-lg border border-outline-variant/40 bg-surface-container p-2 text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface transition"
                title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              >
                {theme === "dark" ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4" />}
              </button>

              {/* User Badge */}
              {user && (
                <div className="flex items-center gap-2 rounded-lg border border-outline-variant/40 bg-surface-container px-3 py-1.5">
                  <UserAvatar name={user.name} role={user.role} />
                  <div className="hidden sm:block">
                    <div className="text-xs font-medium text-on-surface">{user.name}</div>
                    <div className="text-[10px] text-on-surface-variant capitalize">{user.role}</div>
                  </div>
                </div>
              )}
            </div>
          </header>

          {/* Page Content */}
          <main className="min-h-0 flex-1 overflow-auto" aria-label="Page content">
            <Outlet />
          </main>
        </div>
      </div>
    </Tooltip.Provider>
  );
}
