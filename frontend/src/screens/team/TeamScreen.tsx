import { useEffect, useState, type FormEvent } from "react";
import { ArrowClockwiseIcon, EnvelopeSimpleIcon, UsersThreeIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { getMembers, inviteMember } from "@/api";
import { useOrgShell } from "@/app/AppLayout";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { getCurrentOrg, getCurrentOrgName, getCurrentRole } from "@/session";
import { errorText } from "@/lib/errors";

type Member = { userID?: string; email?: string; role?: string };
type PendingInvite = { email?: string; role?: string };

// Mirrors ORG_SEAT_CAP's default in lambda/_org.py; members plus pending invites count.
const SEAT_CAP = 5;

const ROLES = [
  { value: "viewer", label: "Viewer" },
  { value: "editor", label: "Editor" },
  { value: "admin", label: "Admin" },
] as const;

const ROLE_HELP: Record<string, string> = {
  viewer: "Can look at stock and activity.",
  editor: "Can add, adjust and delete stock.",
  admin: "Editor, plus invites people.",
};

const CAN_INVITE = new Set(["admin", "owner"]);


function rows<T>(value: unknown): T[] {
  return Array.isArray(value) ? value.filter((row): row is T => Boolean(row) && typeof row === "object") : [];
}

function initials(email: string): string {
  return (email.trim()[0] ?? "?").toUpperCase();
}

function roleLabel(role: string | undefined): string {
  if (!role) return "Member";
  return role.charAt(0).toUpperCase() + role.slice(1);
}

export function TeamScreen() {
  const { orgEpoch, orgsAvailable, orgsReady } = useOrgShell();
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<PendingInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [sending, setSending] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const orgID = getCurrentOrg();
  const myRole = getCurrentRole();
  // GET /orgs/{id}/members and invites require admin or owner. An unknown role still tries.
  const canManage = !myRole || CAN_INVITE.has(myRole);

  useEffect(() => {
    document.title = "Team | InventoryIQ";
  }, []);

  useEffect(() => {
    let cancelled = false;
    const org = getCurrentOrg();
    setMembers([]);
    setInvites([]);
    setError(null);
    if (!org || !canManage) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void (async () => {
      try {
        const data = await getMembers(org);
        if (cancelled || getCurrentOrg() !== org) return;
        setMembers(rows<Member>(data.members ?? data));
        setInvites(rows<PendingInvite>(data.pendingInvites));
      } catch (err: unknown) {
        if (cancelled || getCurrentOrg() !== org) return;
        setError(errorText(err) || "Could not load the team.");
      } finally {
        if (!cancelled && getCurrentOrg() === org) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orgEpoch, reloadToken, canManage]);

  const used = members.length + invites.length;
  const full = used >= SEAT_CAP;

  async function onInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim().toLowerCase();
    if (!orgID || sending || !address) return;
    setSending(true);
    try {
      await inviteMember(orgID, address, role);
      toast.success(`Invite sent to ${address}`, {
        description: "The link in the email expires in 72 hours.",
      });
      setEmail("");
      setReloadToken((token) => token + 1);
    } catch (err: unknown) {
      toast.error("Invite failed", { description: errorText(err) || "Try again." });
    } finally {
      setSending(false);
    }
  }

  if (!orgsReady) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <PageHeader title="Team" />
        <Skeleton className="h-24 w-full rounded-3xl" />
        <Skeleton className="h-48 w-full rounded-3xl" />
      </div>
    );
  }

  if (!orgsAvailable || !orgID) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <PageHeader title="Team" />
        <div className="flex flex-col items-center gap-2 rounded-3xl border border-dashed border-border px-6 py-14 text-center">
          <UsersThreeIcon className="size-8 text-muted-foreground" />
          <p className="font-medium">Team features aren't available here yet</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            This workspace runs without organizations, so there is no one to invite. Stock and activity work as usual.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <PageHeader
        title="Team"
        description={getCurrentOrgName() || "Who can see and change this organization's stock."}
        actions={
          <Button type="button" variant="outline" disabled={loading} onClick={() => setReloadToken((token) => token + 1)}>
            <ArrowClockwiseIcon />
            Refresh
          </Button>
        }
      />

      {canManage ? (
      <section aria-labelledby="seats-heading" className="flex flex-col gap-2 rounded-3xl border border-border bg-card px-5 py-4">
        <div className="flex items-baseline justify-between">
          <h2 id="seats-heading" className="text-sm font-semibold">
            Seats
          </h2>
          <span id="org-status" className="text-sm tabular-nums">
            {loading ? "…" : `${used} of ${SEAT_CAP} used`}
          </span>
        </div>
        <div className="flex gap-1" aria-hidden>
          {Array.from({ length: SEAT_CAP }, (_, index) => (
            <span
              key={index}
              className={cn(
                "h-2 flex-1 rounded-full",
                index < members.length ? "bg-primary" : index < used ? "bg-primary/40" : "bg-muted",
              )}
            />
          ))}
        </div>
        <p className="text-xs text-muted-foreground">Members and pending invites both take a seat.</p>
      </section>
      ) : null}

      <section aria-labelledby="members-heading" className="overflow-hidden rounded-3xl border border-border bg-card">
        <h2 id="members-heading" className="px-5 pt-4 pb-1 font-heading text-base font-semibold">
          Members
        </h2>
        {loading ? (
          <div className="flex flex-col gap-3 px-5 py-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : !canManage ? (
          <p className="px-5 pt-1 pb-5 text-sm text-muted-foreground">
            Your role here is {roleLabel(myRole)}. Only admins and the owner can see the member list and invite people.
          </p>
        ) : error ? (
          <p role="alert" className="px-5 py-6 text-sm text-destructive">
            {error}
          </p>
        ) : (
          <ul id="member-list" className="divide-y divide-border px-5">
            {members.map((member, index) => {
              const address = member.userID || member.email || "";
              return (
                <li key={address || index} className="flex items-center gap-3 py-3">
                  <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/12 text-sm font-semibold ring-1 ring-primary/25">
                    {initials(address)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{address}</span>
                  <Badge variant={member.role === "owner" ? "default" : "outline"}>{roleLabel(member.role)}</Badge>
                </li>
              );
            })}
            {invites.map((invite, index) => (
              <li key={`invite-${invite.email ?? index}`} className="flex items-center gap-3 py-3">
                <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full border border-dashed border-border text-muted-foreground">
                  <EnvelopeSimpleIcon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{invite.email}</span>
                  <span className="block text-xs text-muted-foreground">Invite sent · {roleLabel(invite.role)}</span>
                </span>
              </li>
            ))}
            {members.length + invites.length === 0 ? (
              <li className="py-6 text-sm text-muted-foreground">No members returned.</li>
            ) : null}
          </ul>
        )}
      </section>

      {canManage ? (
        <section aria-labelledby="invite-heading" className="flex flex-col gap-4 rounded-3xl border border-border bg-card px-5 py-5">
          <h2 id="invite-heading" className="font-heading text-base font-semibold">
            Invite someone
          </h2>
          <form id="invite-form" className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(event) => void onInvite(event)}>
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="invite-email" className="text-xs text-muted-foreground">
                Email
              </Label>
              <Input
                id="invite-email"
                type="email"
                required
                autoComplete="off"
                placeholder="teammate@example.com"
                value={email}
                disabled={sending || full}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:w-36">
              <Label htmlFor="invite-role" className="text-xs text-muted-foreground">
                Role
              </Label>
              <Select
                items={ROLES.map((item) => ({ value: item.value, label: item.label }))}
                value={role}
                disabled={sending || full}
                onValueChange={(next) => {
                  if (typeof next === "string") setRole(next);
                }}
              >
                <SelectTrigger id="invite-role" className="w-full" aria-label="Role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={sending || full || !email.trim()}>
              {sending ? "Sending…" : "Send invite"}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground">
            {full ? `All ${SEAT_CAP} seats are taken.` : ROLE_HELP[role]}
          </p>
        </section>
      ) : null}
    </div>
  );
}
