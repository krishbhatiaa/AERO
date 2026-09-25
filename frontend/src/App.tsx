import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Shell } from "@/components/layout/Shell";
import { Dashboard } from "@/pages/Dashboard";
import { Login } from "@/pages/Login";
import { useAuth } from "@/stores/auth";

// Route-level code splitting
const Events = lazy(() => import("@/pages/Events").then((m) => ({ default: m.Events })));
const EventDetail = lazy(() => import("@/pages/EventDetail").then((m) => ({ default: m.EventDetail })));
const Alerts = lazy(() => import("@/pages/Alerts").then((m) => ({ default: m.Alerts })));
const GlobePage = lazy(() => import("@/pages/Globe").then((m) => ({ default: m.GlobePage })));
const Models = lazy(() => import("@/pages/Models").then((m) => ({ default: m.Models })));
const Datasets = lazy(() => import("@/pages/Datasets").then((m) => ({ default: m.Datasets })));
const Analytics = lazy(() => import("@/pages/Analytics").then((m) => ({ default: m.Analytics })));
const System = lazy(() => import("@/pages/System").then((m) => ({ default: m.System })));
const Platform = lazy(() => import("@/pages/Platform").then((m) => ({ default: m.Platform })));
const NotFound = lazy(() => import("@/pages/NotFound").then((m) => ({ default: m.NotFound })));

function Fallback(): JSX.Element {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-on-surface-variant">Loading...</p>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: JSX.Element }): JSX.Element {
  const isAuthenticated = useAuth((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

export function App(): JSX.Element {
  const isAuthenticated = useAuth((s) => s.isAuthenticated);

  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
        <Route element={<ProtectedRoute><Shell /></ProtectedRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="events" element={<Events />} />
          <Route path="events/:id" element={<EventDetail />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="globe" element={<GlobePage />} />
          <Route path="models" element={<Models />} />
          <Route path="datasets" element={<Datasets />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="system" element={<System />} />
          <Route path="platform" element={<Platform />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
