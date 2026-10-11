/**
 * Old multi-page filenames still linked from emails and bookmarks, mapped to the
 * current SPA route. The caller copies `location.search` onto the target, so
 * `/reset-password.html?token=` and `/accept.html?token=` keep their token.
 */
const LEGACY_HTML_ROUTES = {
  login: "/login",
  "forgot-password": "/forgot-password",
  "reset-password": "/reset-password",
  accept: "/accept",
  dashboard: "/today",
  inventory: "/stock",
  // /add-item decides between the add sheet and an item's sheet (edit payload in sessionStorage).
  "add-item": "/add-item",
  insights: "/insights",
  transactions: "/activity",
  org: "/team",
  suppliers: "/stock",
  forecast: "/insights",
} as const;

export const LEGACY_HTML_PAGES = Object.keys(LEGACY_HTML_ROUTES) as (keyof typeof LEGACY_HTML_ROUTES)[];

/** Pre-redesign extensionless routes. App.tsx redirects each to its replacement. */
export const RENAMED_ROUTES = {
  "/dashboard": "/today",
  "/inventory": "/stock",
  "/transactions": "/activity",
  "/org": "/team",
} as const;

/**
 * Map a browser pathname like `/accept.html` to `/accept`.
 * `/index.html` goes to `/`. Returns null when the path is not a legacy HTML page.
 */
export function legacyRouteForPath(pathname: string): string | null {
  if (pathname === "/index.html") return "/";
  if (!pathname.endsWith(".html")) return null;
  const name = pathname.slice(1, -".html".length);
  return Object.hasOwn(LEGACY_HTML_ROUTES, name)
    ? LEGACY_HTML_ROUTES[name as keyof typeof LEGACY_HTML_ROUTES]
    : null;
}
