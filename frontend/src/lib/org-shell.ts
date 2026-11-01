const EDIT_ROLES: ReadonlySet<string> = new Set(["editor", "admin", "owner"]);

/** Viewers are read-only (no Delete, no edits). No role and no orgs is legacy mode, which has full access. */
export function canEditRole(role: string | undefined, orgCount: number): boolean {
  return role ? EDIT_ROLES.has(role) : orgCount === 0;
}

/** A value opened under one org. After an org switch it reads as closed: it shows the old org's stock. */
export type OrgScoped<T> = { value: T; orgEpoch: number };

export function inCurrentOrg<T>(scoped: OrgScoped<T> | null, orgEpoch: number): T | null {
  return scoped && scoped.orgEpoch === orgEpoch ? scoped.value : null;
}
