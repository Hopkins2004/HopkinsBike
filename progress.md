# Progress — "Sign in with Google" (2026-07-05)

Add Google sign-in alongside the existing email/password login. Baseline: 25/25 tests pass.

## Approach
OAuth 2.0 authorization-code flow implemented with the Python **standard library**
(`urllib`) — no new dependency, so tests/dev keep working offline and nothing to install.
1. `/login/google` → generate a `state` (stored in session), redirect to Google's auth endpoint
   with `scope=openid email profile`.
2. `/login/google/callback` → verify `state`, exchange `code` for tokens at Google's token
   endpoint (server-to-server, uses the client secret), then call Google's OIDC `userinfo`
   endpoint with the access token to get the verified email.
3. Find-or-create the user by email (Google verifies the email, so linking by email is safe),
   set `session['username']`, redirect to /history.

## Details / decisions
- Config: `HOPKINS_GOOGLE_CLIENT_ID` / `HOPKINS_GOOGLE_CLIENT_SECRET` (both empty by default).
  Google sign-in is enabled only when both are set; the button and routes no-op otherwise.
- New Google users get an **unusable** password hash (`generate_password_hash` of a random
  token) so the password-login path can never match — they must use Google.
- Routes are always registered (button hidden via `google_enabled` when unconfigured), so the
  URL map is deterministic → regenerate the urlmap fixture once.
- Security: `state` (CSRF) checked on callback; token/userinfo calls over TLS; `email_verified`
  required; callbacks are GET so the existing CSRF-on-POST guard is unaffected; SameSite=Lax lets
  the state cookie survive Google's top-level redirect back.
- UI: "Sign in with Google" button (official 4-colour G) under the form on login + register,
  shown only when configured. Styles added to static/login.css (shared by both pages).

## Verification — DONE
- tests/test_google_auth.py (6 new): disabled-by-default guard + hidden button; button shown when
  configured; /login/google redirects to accounts.google.com with correct client_id/scope and the
  state matching the session; bad-state callback blocked (not signed in); happy path (userinfo
  mocked) provisions a verified 'user' and sets the session; a Google login for an existing email
  links to that account (no duplicate). Full suite: 31/31 pass.
- Browser: /login with Google configured renders the 4-colour Google button under an "or" divider;
  clicking it navigates all the way to accounts.google.com (errors only because the demo client id
  is fake — the redirect wiring is correct). Unconfigured app is unchanged (no button).
- urlmap fixture regenerated (+/login/google, +/login/google/callback).
- README documents the two env vars and the Google Cloud Console setup steps.
