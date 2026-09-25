import { Link } from "react-router-dom";
import { Home, AlertCircle } from "lucide-react";

export function NotFound(): JSX.Element {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-container">
          <AlertCircle className="h-8 w-8 text-on-surface-variant" />
        </div>
        <h1 className="text-3xl font-bold text-on-surface">404</h1>
        <p className="mt-2 text-sm text-on-surface-variant">The page you're looking for doesn't exist.</p>
        <Link to="/" className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary transition hover:opacity-90">
          <Home className="h-4 w-4" /> Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
