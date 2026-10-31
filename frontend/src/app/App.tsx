import { Navigate, Route, BrowserRouter, Routes, useLocation, useNavigate } from "react-router";
import { AppLayout } from "@/app/AppLayout";
import { legacyRouteForPath, RENAMED_ROUTES } from "@/app/legacyHtml";
import { HOME_ROUTE } from "@/app/routes";
import { isLocalPreview, SESSION_EXPIRED_EVENT } from "@/api";
import { ErrorBoundary } from "@/components/error-boundary";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "next-themes";
import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";

// Each screen is its own chunk, so sign-in does not download the stock screen.
const AcceptScreen = lazy(() => import("@/screens/AcceptScreen").then((m) => ({ default: m.AcceptScreen })));
const ForgotPasswordScreen = lazy(() => import("@/screens/ForgotPasswordScreen").then((m) => ({ default: m.ForgotPasswordScreen })));
const LoginScreen = lazy(() => import("@/screens/LoginScreen").then((m) => ({ default: m.LoginScreen })));
const OnboardingScreen = lazy(() => import("@/screens/onboarding/OnboardingScreen").then((m) => ({ default: m.OnboardingScreen })));
const ResetPasswordScreen = lazy(() => import("@/screens/ResetPasswordScreen").then((m) => ({ default: m.ResetPasswordScreen })));

/**
 * A lazy screen whose chunk can be loaded ahead of time. Once loaded it renders directly instead of through lazy(),
 * which would still suspend once and flash the skeleton inside a page cross-fade.
 */
function preloadable(load: () => Promise<ComponentType>): { Screen: ComponentType; preload: () => Promise<unknown> } {
  let Loaded: ComponentType | undefined;
  const preload = () => load().then((component) => (Loaded = component));
  const Lazy = lazy(() => preload().then((component) => ({ default: component })));
  // Picked once per mount: swapping Lazy for Loaded mid-life would remount the screen and lose its state.
  function Screen() {
    const [Component] = useState(() => Loaded ?? Lazy);
    return <Component />;
  }
  return { Screen, preload };
}

// The signed-in screens, also preloaded at idle once signed in so page switches don't wait on the network.
const SIGNED_IN = {
  activity: preloadable(() => import("@/screens/activity/ActivityScreen").then((m) => m.ActivityScreen)),
  insights: preloadable(() => import("@/screens/InsightsScreen").then((m) => m.InsightsScreen)),
  stock: preloadable(() => import("@/screens/stock/StockScreen").then((m) => m.StockScreen)),
  team: preloadable(() => import("@/screens/team/TeamScreen").then((m) => m.TeamScreen)),
  today: preloadable(() => import("@/screens/today/TodayScreen").then((m) => m.TodayScreen)),
};
const ActivityScreen = SIGNED_IN.activity.Screen;
const InsightsScreen = SIGNED_IN.insights.Screen;
const StockScreen = SIGNED_IN.stock.Screen;
const TeamScreen = SIGNED_IN.team.Screen;
const TodayScreen = SIGNED_IN.today.Screen;

/** Loads every signed-in screen once the browser is idle. A failed chunk (stale deploy) is left to the route's own load. */
function usePreloadScreens() {
  useEffect(() => {
    const run = () => {
      for (const { preload } of Object.values(SIGNED_IN)) preload().catch(() => {});
    };
    if (typeof requestIdleCallback === "function") {
      const id = requestIdleCallback(run);
      return () => cancelIdleCallback(id);
    }
    const timer = setTimeout(run, 1000);
    return () => clearTimeout(timer);
  }, []);
}
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

/** A 401 in api.ts clears the session; this sends the user to the login form without a full page load. */
function SessionExpiredRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    const onExpired = () => void navigate("/login?expired=1", { replace: true });
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [navigate]);
  return null;
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
  usePreloadScreens();
  if (!getUserEmail()) return <Navigate to="/login" replace />;
  return <AppLayout />;
}

/** Signed in, but full screen: onboarding runs before the app shell. */
function OnboardingRoute() {
  applyLocalPreview();
  if (!getUserEmail()) return <Navigate to="/login" replace />;
  return <OnboardingScreen />;
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
      <Route path="/onboarding" element={<OnboardingRoute />} />
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
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
      scriptProps={{ type: "application/json" }}
    >
      {/* Sync navigations, so the nav cross-fade (AppLayout useNavClick) can flushSync the new page inside startViewTransition. */}
      <BrowserRouter useTransitions={false}>
        <SessionExpiredRedirect />
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
