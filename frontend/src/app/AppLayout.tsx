import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import {
  HouseSimpleIcon,
  PackageIcon,
  PulseIcon,
  UsersThreeIcon,
  type IconProps,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  ensureOrgContext,
  getOrgs,
  isLocalPreview,
  switchOrg,
  type OrgRecord,
} from "@/api";
import { InventoryProvider, useInventory } from "@/app/inventory-store";
import { AccountMenu } from "@/components/account-menu";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { countByLevel } from "@/lib/dashboardStats";
import { cn } from "@/lib/utils";
import { CONFIG } from "@/config";
import {
  clearSession,
  getCurrentOrg,
  getCurrentOrgName,
  getCurrentRole,
  getSessionToken,
  getUserEmail,
  setCurrentOrgName,
  setLocalLogout,
} from "@/session";

export type OrgShellContextValue = {
  orgs: OrgRecord[];
  /** True once GET /orgs answered with at least one org. False in legacy (no-org) mode. */
  orgsAvailable: boolean;
  /** False until the first GET /orgs settles (success or 403/404). */
  orgsReady: boolean;
  /** Bumps after a successful org switch so later screens can refetch. */
  orgEpoch: number;
  refreshOrgs: () => Promise<void>;
};

const OrgShellContext = createContext<OrgShellContextValue | null>(null);

export function useOrgShell(): OrgShellContextValue {
  const value = useContext(OrgShellContext);
  if (!value) {
    throw new Error("useOrgShell must be used inside the authenticated layout");
  }
  return value;
}

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<IconProps>;
};

const NAV: readonly NavItem[] = [
  { to: "/today", label: "Today", icon: HouseSimpleIcon },
  { to: "/stock", label: "Stock", icon: PackageIcon },
  { to: "/activity", label: "Activity", icon: PulseIcon },
  { to: "/team", label: "Team", icon: UsersThreeIcon },
];

function roleText(role: string | undefined): string {
  return role ? role.charAt(0).toUpperCase() + role.slice(1) : "";
}

export function AppLayout() {
  const navigate = useNavigate();
  const email = getUserEmail();
  const [orgs, setOrgs] = useState<OrgRecord[]>([]);
  const [orgsReady, setOrgsReady] = useState(false);
  const [orgEpoch, setOrgEpoch] = useState(0);
  const [switching, setSwitching] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const refreshOrgs = useCallback(async () => {
    try {
      const data = await getOrgs();
      setOrgs(data.orgs ?? []);
    } catch {
      // GET /orgs is 403/404 where org tables are not deployed: legacy mode, Team hidden.
      setOrgs([]);
    } finally {
      setOrgsReady(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await ensureOrgContext();
      } catch {
        /* org APIs may not be deployed yet */
      }
      if (!cancelled) await refreshOrgs();
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshOrgs]);

  const changeOrg = useCallback(
    async (orgID: string) => {
      if (switching || orgID === getCurrentOrg()) return;
      setSwitching(true);
      try {
        await switchOrg(orgID);
        const chosen = orgs.find((org) => org.orgID === orgID);
        if (chosen?.name) setCurrentOrgName(chosen.name);
        await refreshOrgs();
        setOrgEpoch((epoch) => epoch + 1);
        toast.success(`Switched to ${chosen?.name || "organization"}`);
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "Failed to switch organization");
      } finally {
        setSwitching(false);
      }
    },
    [orgs, refreshOrgs, switching],
  );

  const logout = useCallback(async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    const token = getSessionToken();
    if (token) {
      try {
        await fetch(`${CONFIG.AUTH_ENDPOINT}/logout`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Session-Token": token },
        });
      } catch {
        // Network error on logout is non-fatal — always clear local session
      }
    }
    clearSession();
    if (isLocalPreview()) setLocalLogout();
    navigate("/login", { replace: true });
  }, [loggingOut, navigate]);

  const shell = useMemo<OrgShellContextValue>(
    () => ({ orgs, orgsAvailable: orgs.length > 0, orgsReady, orgEpoch, refreshOrgs }),
    [orgs, orgsReady, orgEpoch, refreshOrgs],
  );

  const account = {
    email,
    loggingOut,
    onLogout: () => void logout(),
  };

  return (
    <OrgShellContext.Provider value={shell}>
      <InventoryProvider orgEpoch={orgEpoch}>
        <div className="min-h-svh bg-background text-foreground md:flex">
          <a
            href="#main"
            className="sr-only z-50 rounded-xl bg-background px-3 py-2 text-sm font-medium focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:ring-[3px] focus:ring-ring/50"
          >
            Skip to content
          </a>
          <aside className="sticky top-0 hidden h-svh w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground md:flex">
            <div className="flex h-16 items-center px-5">
              <Brand />
            </div>
            <OrgSwitcher orgs={orgs} switching={switching} onSwitch={(id) => void changeOrg(id)} />
            <SideNav showTeam={orgs.length > 0} />
            <div className="mt-auto border-t border-sidebar-border p-3">
              <AccountMenu {...account} variant="sidebar" />
            </div>
          </aside>
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-background/90 px-4 backdrop-blur-md md:hidden">
              <Brand />
              <div className="ml-auto min-w-0">
                <AccountMenu
                  {...account}
                  orgPicker={{
                    orgs,
                    current: getCurrentOrg(),
                    switching,
                    onSwitch: (id) => void changeOrg(id),
                  }}
                />
              </div>
            </header>
            <main
              id="main"
              tabIndex={-1}
              className="flex-1 px-4 pt-5 pb-28 outline-none md:px-8 md:pt-8 md:pb-12"
            >
              <div className="mx-auto w-full max-w-6xl">
                <Outlet />
              </div>
            </main>
          </div>
          <TabBar showTeam={orgs.length > 0} />
        </div>
      </InventoryProvider>
    </OrgShellContext.Provider>
  );
}

function Brand() {
  return (
    <span className="flex items-center gap-2.5 font-heading text-base font-semibold tracking-tight">
      <svg viewBox="0 0 24 24" aria-hidden className="size-7 shrink-0">
        <rect width="24" height="24" rx="7" className="fill-primary" />
        <rect x="5.5" y="13" width="3" height="5.5" rx="1" className="fill-primary-foreground" />
        <rect x="10.5" y="9" width="3" height="9.5" rx="1" className="fill-primary-foreground" />
        <rect x="15.5" y="5.5" width="3" height="13" rx="1" className="fill-primary-foreground" />
      </svg>
      InventoryIQ
    </span>
  );
}

function OrgSwitcher({
  orgs,
  switching,
  onSwitch,
}: {
  orgs: OrgRecord[];
  switching: boolean;
  onSwitch: (orgID: string) => void;
}) {
  const current = getCurrentOrg();
  const selected = orgs.some((org) => org.orgID === current) ? current : null;
  const items = orgs.map((org) => ({ value: org.orgID, label: org.name || org.orgID }));
  const role = roleText(orgs.find((org) => org.orgID === current)?.role ?? getCurrentRole());
  const fallbackLabel = getCurrentOrgName() || "Workspace";

  return (
    <div className="px-3 pb-4" id="org-switcher">
      <Label className="mb-1.5 px-2 text-xs text-muted-foreground">Organization</Label>
      {orgs.length > 0 ? (
        <Select
          items={items}
          value={selected}
          disabled={switching}
          onValueChange={(next) => {
            if (typeof next === "string") onSwitch(next);
          }}
        >
          <SelectTrigger className="w-full" aria-label="Organization">
            <SelectValue placeholder={fallbackLabel} />
          </SelectTrigger>
          <SelectContent>
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <p className="truncate px-2 text-sm font-medium">{fallbackLabel}</p>
      )}
      {role ? <p className="mt-1.5 px-2 text-xs text-muted-foreground">Your role: {role}</p> : null}
    </div>
  );
}

function useRestockCount(): number {
  const { items } = useInventory();
  return useMemo(() => {
    const counts = countByLevel(items);
    return counts.out + counts.low;
  }, [items]);
}

function visibleNav(showTeam: boolean): readonly NavItem[] {
  return showTeam ? NAV : NAV.filter((item) => item.to !== "/team");
}

function SideNav({ showTeam }: { showTeam: boolean }) {
  const restock = useRestockCount();
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5 px-3">
      {visibleNav(showTeam).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            cn(
              "group flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-sidebar-ring/50",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
            )
          }
        >
          {({ isActive }) => (
            <>
              <item.icon className="size-[18px]" weight={isActive ? "fill" : "regular"} />
              {item.label}
              {item.to === "/today" && restock > 0 ? (
                <span
                  className="ml-auto min-w-5 rounded-full bg-warning px-1.5 text-center text-xs leading-5 font-semibold text-background tabular-nums"
                  aria-label={`${restock} to restock`}
                >
                  {restock}
                </span>
              ) : null}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function TabBar({ showTeam }: { showTeam: boolean }) {
  const restock = useRestockCount();
  const items = visibleNav(showTeam);
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
    >
      <ul className="grid" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "relative flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium outline-none focus-visible:bg-muted",
                  isActive ? "text-foreground" : "text-muted-foreground",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      "flex h-7 w-12 items-center justify-center rounded-full transition-colors",
                      isActive && "bg-primary/12",
                    )}
                  >
                    <item.icon className="size-5" weight={isActive ? "fill" : "regular"} />
                  </span>
                  {item.label}
                  {item.to === "/today" && restock > 0 ? (
                    <span
                      className="absolute top-1.5 left-1/2 ml-2 min-w-4 rounded-full bg-warning px-1 text-center text-[10px] leading-4 font-semibold text-background tabular-nums"
                      aria-label={`${restock} to restock`}
                    >
                      {restock}
                    </span>
                  ) : null}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
