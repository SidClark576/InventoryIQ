export type Role = 'viewer' | 'editor' | 'admin' | 'owner';

export const SESSION_KEYS = {
  sessionToken: 'sessionToken',
  userEmail: 'userEmail',
  currentOrg: 'currentOrg',
  currentOrgName: 'currentOrgName',
  currentRole: 'currentRole',
  editItem: 'iq_editItem',
  localLogout: 'iq_local_logout',
  inviteToken: 'iq_inviteToken',
} as const;

export function getSessionToken(): string {
  return sessionStorage.getItem(SESSION_KEYS.sessionToken) || '';
}

export function setSessionToken(token: string): void {
  sessionStorage.setItem(SESSION_KEYS.sessionToken, token);
}

export function getUserEmail(): string {
  return sessionStorage.getItem(SESSION_KEYS.userEmail) || '';
}

export function setUserEmail(email: string): void {
  sessionStorage.setItem(SESSION_KEYS.userEmail, email);
}

export function getCurrentOrg(): string {
  return sessionStorage.getItem(SESSION_KEYS.currentOrg) || '';
}

export function setCurrentOrg(orgID: string): void {
  sessionStorage.setItem(SESSION_KEYS.currentOrg, orgID);
}

export function getCurrentOrgName(): string {
  return sessionStorage.getItem(SESSION_KEYS.currentOrgName) || '';
}

export function setCurrentOrgName(name: string): void {
  sessionStorage.setItem(SESSION_KEYS.currentOrgName, name);
}

export function getCurrentRole(): string {
  return sessionStorage.getItem(SESSION_KEYS.currentRole) || '';
}

export function setCurrentRole(role: string): void {
  sessionStorage.setItem(SESSION_KEYS.currentRole, role);
}

export function getEditItem(): string | null {
  return sessionStorage.getItem(SESSION_KEYS.editItem);
}

export function setEditItem(json: string): void {
  sessionStorage.setItem(SESSION_KEYS.editItem, json);
}

export function clearEditItem(): void {
  sessionStorage.removeItem(SESSION_KEYS.editItem);
}

export function getLocalLogout(): string | null {
  return sessionStorage.getItem(SESSION_KEYS.localLogout);
}

export function setLocalLogout(): void {
  sessionStorage.setItem(SESSION_KEYS.localLogout, '1');
}

export function getInviteToken(): string | null {
  return sessionStorage.getItem(SESSION_KEYS.inviteToken);
}

export function setInviteToken(token: string): void {
  sessionStorage.setItem(SESSION_KEYS.inviteToken, token);
}

export function clearInviteToken(): void {
  sessionStorage.removeItem(SESSION_KEYS.inviteToken);
}

export function clearSession(): void {
  sessionStorage.clear();
}
