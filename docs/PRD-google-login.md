# PRD: Google Sign-In

> Status: Draft · Mode: Thorough · Owner: Sidney · Date: 2026-07-21

## TL;DR

Add "Sign in with Google" as a second way into InventoryIQ, sitting above the existing email/password form as the recommended path. Existing accounts are untouched — this is additive, not a replacement, and requires no changes to the org/RBAC model already in flight.

## Background

- Today, `login.html` has one way in: email + password, with a separate tabbed "Create Account" form on the same page. Registration requires an 8+ character password with upper/lower/digit.
- Auth is a hand-rolled, stateless HS256 JWT (no external JWT library) signed by `Authentication.mjs`, verified independently by `Proxy.py` and `Authorizer.mjs` using a shared secret. The client holds the token in `sessionStorage` and sends it as `X-Session-Token`.
- Accounts are keyed by lowercased email (`Users` table, `Email` as primary key) — there's no separate internal user ID today.
- A separate draft PRD (`PRD-org-membership-rbac.md`) explicitly excluded Google/social login from its scope. This PRD is independent of that one — it works the same way today's signup does (personal org per new user) and doesn't block on or wait for the org system shipping.

## Problem & Target Users

- **Who:** Anyone signing up or logging in — especially users who'd rather not create and remember another password, and business owners evaluating the product who drop off at "yet another account to set up."
- **Pain:** Password creation is friction. Users forget passwords, reuse weak ones, or abandon signup rather than think one up.
- **Impact:** Slower signup conversion, more forgot-password support load, weaker account security for users who reuse passwords elsewhere.

## Goals & Success Metrics

| Goal | Metric |
|------|--------|
| Reduce signup friction | % of new accounts created via Google vs. password |
| Faster path to first login | Time from landing on login page to reaching dashboard |
| No regression for existing users | 0 password-account users forced to change how they log in |
| Fewer password resets | Drop in forgot-password volume post-launch |

## Solution Overview

- A "Sign in with Google" button appears at the top of the login/register panel, above a divider ("or continue with email"), with the existing email/password form unchanged below it.
- Clicking it runs the standard Google sign-in flow and returns control to InventoryIQ with the user's verified Google identity (name, email).
- On the backend, this identity is exchanged for the same internal session token every other login path produces — the rest of the app (dashboard, inventory, org switching, RBAC) doesn't know or care whether the session came from a password or from Google.
- **New email, no existing account:** an account and personal org are created automatically — identical to today's email/password signup, minus the password step.
- **Email matches an existing password account:** since Google has already verified the email is real, we treat it as the same person and link automatically — no extra confirmation step, no separate "Google account" vs "password account."
- **Google-only accounts** (never set a password) don't get a "Forgot password" option — that flow tells them to use Google instead, rather than emailing a reset link for a password that was never set.
- Open to any Google account — no domain restriction, matching today's open self-serve signup.

## User Experience

1. User lands on the login page and sees the Google button as the first, most prominent action, with email/password still fully available below.
2. Clicking Google walks through the standard Google account picker/consent screen (outside our app).
3. On return, the same success path as password login runs: session established, redirect to the dashboard. No new "Google-specific" screens inside the app.
4. If something goes wrong (popup closed, network error), the existing inline error-message pattern on the login page is reused — same visual treatment as a failed password login, just different wording.
5. A user who already has a password account and later clicks "Sign in with Google" with the same email lands in their existing account and existing org(s) — nothing about their data, org membership, or history changes.
6. A Google-only user who clicks "Forgot password" is told to sign in with Google instead, rather than being sent a reset email.

## Requirements

- Google Sign-In button visible on both the Login and Register tabs, positioned above the existing form with a visual divider.
- Successful Google sign-in produces the same session as password login (same storage, same expiry behavior, same redirect).
- New Google sign-in with an unrecognized email creates an account + personal org, same as today's registration.
- Google sign-in with an email matching an existing account logs into that existing account without requiring the password.
- Accounts that have never set a password do not see a working "Forgot password" flow — they're directed to sign in with Google instead.
- Existing password-based login, registration, and password reset continue to work exactly as they do today, unchanged.
- No domain allowlist — any Google account can sign in or sign up.
- Failure states (user cancels, Google error) surface an inline error message consistent with existing login error styling — never a silent failure.

## Out of Scope

- Any other social/SSO provider (Facebook, Microsoft, Apple, SAML) — Google only for this release.
- Letting a Google-only user set a password later (a "add a password to your account" settings option) — not included here.
- Org-invite flows changing to accommodate Google — invited users still accept invites exactly as they do today; this PRD doesn't touch that system.
- Enterprise domain restrictions or org-level "require Google sign-in" policy controls.

## Open Questions

- Should the register-tab Google button say "Sign up with Google" while the login-tab one says "Sign in with Google," or use identical copy in both places?
- Does the SNS stock-alert email auto-subscription (currently tied to registration) still fire for accounts created via Google? Assumed yes, unconfirmed.
- What should happen, if anything, to the "Remember device" checkbox next to password login — does it apply to Google sessions too, or is it password-flow-only?

## Assumptions

- Google is additive, not a replacement for password login — **high confidence** (explicit user decision).
- Auto-link by verified email, no extra confirmation step — **high confidence** (explicit user decision).
- Ships independently of the org/RBAC PRD, using today's personal-org-per-user model — **high confidence** (explicit user decision).
- Google button placed above the existing form as the recommended path — **high confidence** (explicit user decision).
- Open to any Google account, no domain allowlist — **high confidence** (explicit user decision).
- "Remember device" checkbox behavior for Google sessions — **low confidence**, flagged as an open question above.
