import { Navigate, Route, BrowserRouter, Routes, useLocation } from "react-router";
import { AppLayout } from "@/app/AppLayout";
import { legacyRouteForPath, RENAMED_ROUTES } from "@/app/legacyHtml";
import { HOME_ROUTE } from "@/app/routes";
import { isLocalPreview } from "@/api";
import { ErrorBoundary } from "@/components/error-boundary";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "next-themes";
import { lazy, Suspense } from "react";

// Each screen is its own chunk, so sign-in does not download the stock screen.
const AcceptScreen = lazy(() => import("@/screens/AcceptScreen").then((m) => ({ default: m.AcceptScreen })));
const ActivityScreen = lazy(() => import("@/screens/activity/ActivityScreen").then((m) => ({ default: m.ActivityScreen })));
const ForgotPasswordScreen = lazy(() => import("@/screens/ForgotPasswordScreen").then((m) => ({ default: m.ForgotPasswordScreen })));
const InsightsScreen = lazy(() => import("@/screens/InsightsScreen").then((m) => ({ default: m.InsightsScreen })));
const LoginScreen = lazy(() => import("@/screens/LoginScreen").then((m) => ({ default: m.LoginScreen })));
const ResetPasswordScreen = lazy(() => import("@/screens/ResetPasswordScreen").then((m) => ({ default: m.ResetPasswordScreen })));
const StockScreen = lazy(() => import("@/screens/stock/StockScreen").then((m) => ({ default: m.StockScreen })));
const TeamScreen = lazy(() => import("@/screens/team/TeamScreen").then((m) => ({ default: m.TeamScreen })));
const TodayScreen = lazy(() => import("@/screens/today/TodayScreen").then((m) => ({ default: m.TodayScreen })));
import { getEditItem, getLocalLogout, getUserEmail, setUserEmail } from "@/session";

/**
 * Localhost preview gate: signs in as
 * preview@localhost unless iq_local_logout is set.
 */
function applyLocalPreview(): void {
  if (isLocalPreview() && !getUserEmail() && !getLocalLogout()) {
    setUserEmail("preview@localhost");
  }
}

function LegacyHtmlRedirect() {
  const location = useLocation();
  const next = legacyRouteForPath(location.pathname);
  if (!next) return null;
  return (
    <Navigate
      to={{ pathname: next, search: location.search, hash: location.hash }}
      replace
    />
  );
}

/** Old route renamed in the redesign; keeps the query string (e.g. Stock filters). */
function RenamedRedirect({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={{ pathname: to, search: location.search, hash: location.hash }} replace />;
}

/**
 * /add-item used to be its own page. A barcode scan stored a prefill in
 * `iq_editItem`; Edit stored the whole item. The prefill stays in sessionStorage
 * for the Stock add sheet; an existing item opens its own sheet instead.
 */
function AddItemRedirect() {
  const raw = getEditItem();
  let itemID = "";
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (parsed && typeof parsed === "object" && "itemID" in parsed) {
      itemID = String((parsed as { itemID?: unknown }).itemID ?? "");
    }
  } catch {
    // A malformed payload just opens an empty add sheet.
  }
  const search = itemID ? `?item=${encodeURIComponent(itemID)}` : "?new=1";
  return <Navigate to={{ pathname: "/stock", search }} replace />;
}

function HomeRedirect() {
  applyLocalPreview();
  return <Navigate to={getUserEmail() ? HOME_ROUTE : "/login"} replace />;
}

function LoginRoute() {
  if (isLocalPreview() && !getLocalLogout()) {
    setUserEmail("preview@localhost");
  }
  if (getUserEmail()) return <Navigate to={HOME_ROUTE} replace />;
  return <LoginScreen />;
}

function RequireAuth() {
  applyLocalPreview();
  if (!getUserEmail()) return <Navigate to="/login" replace />;
  return <AppLayout />;
}

function AppRoutes() {
  const location = useLocation();
  if (legacyRouteForPath(location.pathname)) {
    return <LegacyHtmlRedirect />;
  }
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/forgot-password" element={<ForgotPasswordScreen />} />
      <Route path="/reset-password" element={<ResetPasswordScreen />} />
      <Route path="/accept" element={<AcceptScreen />} />
      <Route element={<RequireAuth />}>
        <Route path="/today" element={<TodayScreen />} />
        <Route path="/stock" element={<StockScreen />} />
        <Route path="/activity" element={<ActivityScreen />} />
        <Route path="/team" element={<TeamScreen />} />
        <Route path="/insights" element={<InsightsScreen />} />
        <Route path="/add-item" element={<AddItemRedirect />} />
        {Object.entries(RENAMED_ROUTES).map(([from, to]) => (
          <Route key={from} path={from} element={<RenamedRedirect to={to} />} />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  // ThemeProvider's inline script would need 'unsafe-inline' in the CSP; public/theme-init.js applies the class before paint instead.
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      scriptProps={{ type: "application/json" }}
    >
      <BrowserRouter>
        <ErrorBoundary>
          {/* Signed-out screens only; the app layout has its own skeleton fallback around its Outlet. */}
          <Suspense fallback={null}>
            <AppRoutes />
          </Suspense>
        </ErrorBoundary>
      </BrowserRouter>
      <Toaster />
    </ThemeProvider>
  );
}
