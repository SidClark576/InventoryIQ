import { BuildingsIcon, CaretUpDownIcon, SignOutIcon } from "@phosphor-icons/react";
import type { OrgRecord } from "@/api";
import { ThemeRadioGroup } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type OrgPicker = {
  orgs: OrgRecord[];
  current: string;
  switching: boolean;
  onSwitch: (orgID: string) => void;
};

type AccountMenuProps = {
  email: string;
  loggingOut: boolean;
  onLogout: () => void;
  /** Sidebar trigger fills the width and opens upward. */
  variant?: "header" | "sidebar";
  /** Organization choices, shown in the menu where the sidebar switcher is hidden. */
  orgPicker?: OrgPicker;
};

function initialOf(email: string): string {
  return (email.trim()[0] ?? "?").toUpperCase();
}

export function AccountMenu({
  email,
  loggingOut,
  onLogout,
  variant = "header",
  orgPicker,
}: AccountMenuProps) {
  const sidebar = variant === "sidebar";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            className={cn(
              "h-9 gap-2 pr-3 pl-1.5",
              sidebar ? "h-11 w-full justify-start rounded-2xl" : "max-w-64",
            )}
            aria-label={email ? `Account menu for ${email}` : "Account menu"}
          />
        }
      >
        <span
          aria-hidden
          className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-foreground ring-1 ring-primary/25"
        >
          {initialOf(email)}
        </span>
        <span
          id="nav-email"
          className={cn("truncate text-sm text-muted-foreground", sidebar ? "flex-1 text-left" : "hidden sm:inline")}
        >
          {email}
        </span>
        {sidebar ? <CaretUpDownIcon aria-hidden className="text-muted-foreground" /> : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align={sidebar ? "start" : "end"}
        side={sidebar ? "top" : "bottom"}
        className="w-64"
      >
        <DropdownMenuGroup>
          <DropdownMenuLabel className="truncate">{email || "Signed in"}</DropdownMenuLabel>
        </DropdownMenuGroup>
        {orgPicker && orgPicker.orgs.length > 0 ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel>Organization</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={orgPicker.current}
                onValueChange={(next) => {
                  if (typeof next === "string" && next !== orgPicker.current) orgPicker.onSwitch(next);
                }}
              >
                {orgPicker.orgs.map((org) => (
                  <DropdownMenuRadioItem key={org.orgID} value={org.orgID} disabled={orgPicker.switching}>
                    <BuildingsIcon />
                    <span className="truncate">{org.name || org.orgID}</span>
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuGroup>
          </>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>Theme</DropdownMenuLabel>
          <ThemeRadioGroup />
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={loggingOut} onClick={onLogout}>
          <SignOutIcon />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
