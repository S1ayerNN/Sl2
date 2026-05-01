# MyAstro QA & Security Audit Report

**Date:** 2026-05-01
**Branch:** `fix/qa-security-audit-fixes`
**Status:** All findings addressed

---

## Summary

### QA: 7 API bugs + 5 frontend bugs found

**Most impactful:**
- **Q1**: `POST /auth/dev-login` accessible if `DEBUG=true` in production -- full auth bypass
- **Q2**: `birth_time` can't be cleared (empty string fails regex)
- **Q6**: New `PATCH /profile/family/{id}` had no `birth_time` format validation

### Frontend bugs:
- **F4**: No refresh token logic -- users get logged out after 15 minutes

### Security: IDOR is clean, 2 critical findings

**IDOR verdict: All endpoints properly check resource ownership.** Cross-user access is not possible.

**Critical findings:**
- **S1 (CRITICAL)**: `dev-login` endpoint gives unauthenticated JWT when `DEBUG=true`. If production `.env` has `DEBUG=true`, anyone can get a token.
- **S2 (HIGH)**: Debug endpoints leak AI config, allow free horoscope generation bypassing all limits
- **V1 (HIGH)**: XSS via family member names -- names are inserted via `innerHTML` string concatenation without escaping. `<img src=x onerror=alert(1)>` as a name would execute.

---

## Fixes Applied

### S1 (CRITICAL): Dev-login auth bypass

**Problem:** `POST /auth/dev-login` was always registered as a route and only checked `settings.DEBUG` at runtime. If production `.env` had `DEBUG=true`, anyone could get a valid JWT.

**Fix:**
- Dev-login route is now conditionally registered only when `settings.DEBUG=true` at import time (`app/api/auth.py`)
- Runtime defense-in-depth check still present
- `.env.example` now defaults to `DEBUG=false` with a security comment

**Files:** `app/api/auth.py`, `.env.example`

### S2 (HIGH): Debug endpoint exposure

**Problem:** Debug router (`/api/v1/debug/*`) was always included in the app, leaking AI config (models, API URL, temperature) and allowing free horoscope generation.

**Fix:**
- Debug router is now conditionally imported and included only when `settings.DEBUG=true` in `app/main.py`
- When `DEBUG=false`, the routes don't exist at all -- no 403, just 404

**Files:** `app/main.py`

### V1 (HIGH): XSS via innerHTML

**Problem:** Family member names, horoscope history text, and other user-generated content were inserted into the DOM using string concatenation with `innerHTML`, allowing script injection.

**Fix:**
- Added `esc()` HTML escaping utility function in the frontend
- All user-generated content in `loadFamily()`, `loadHistory()`, and `loadProfileScreen()` now uses `esc()` before insertion into `innerHTML`
- Interest tags in profile also escaped
- Safe patterns (like `textContent`) were already used in some places and left as-is

**Files:** `web/index.html`

### Q2: birth_time can't be cleared

**Problem:** Sending `birth_time: ""` to `PATCH /profile/me` failed with "Invalid time format" because the empty string didn't match the `HH:MM` regex.

**Fix:**
- Empty string is now explicitly handled before regex validation
- `birth_time: ""` sets the field to `null` (cleared)
- Same pattern applied to `birth_place`, `email` (clearing supported)

**Files:** `app/api/profile.py`

### Q6: Family member PATCH with birth_time validation

**Problem:** No `PATCH /profile/family/{id}` endpoint existed, and the POST endpoint had no `birth_time` format validation.

**Fix:**
- Added `PATCH /profile/family/{member_id}` endpoint with full validation:
  - `birth_time` format validation (`HH:MM` regex + range check)
  - Empty string to clear `birth_time`
  - Name length validation (2-100 chars)
  - Relation/gender enum validation
  - Birth date format validation with zodiac recalculation
  - Interest validation against catalog
  - IDOR protection (owner_id check)
- Added `birth_time` format validation to POST `/profile/family` as well
- Added `FamilyMemberUpdate` schema

**Files:** `app/api/profile.py`, `app/schemas/user.py`

### F4: Refresh token auto-refresh

**Problem:** Frontend only stored `access_token` (15-minute TTL). When it expired, users were immediately logged out with no attempt to refresh.

**Fix:**
- Frontend now stores both `access_token` and `refresh_token` in `localStorage`
- `api()` function intercepts 401 responses and attempts token refresh via `POST /auth/refresh`
- On successful refresh, the original request is retried transparently
- On failed refresh (expired refresh token), user is logged out
- `logout()` clears both tokens
- `devLogin()` stores both tokens

**Files:** `web/index.html`

### UI: "He заполнено" placeholder replacement

**Problem:** Empty profile fields showed misleading placeholder text (e.g., "14:30", "Москва") that looked like real data.

**Fix:**
- Profile fields now display as read-only view with "Не заполнено" text (styled in `--neon` color, italic) when empty
- Clicking any field opens an inline editor with save/cancel/clear buttons
- Each field can be independently edited and saved
- Clear button allows removing field values
- Interests have their own "Save interests" button
- CSS class `.field-empty` provides visual encouragement to click

**Files:** `web/index.html`

### .env.example hardened

**Problem:** `DEBUG=true` was the default in `.env.example`, making it easy to deploy with debug mode on.

**Fix:** Default changed to `DEBUG=false` with a security comment.

**Files:** `.env.example`

---

## What Was Already Well Done

- **IDOR protection** is solid across all 11 endpoints
- **JWT implementation** is proper (type checking, blacklisting, JTI)
- **Telegram auth** has HMAC + replay protection (5-minute window)
- **PII encryption** with Fernet is correctly implemented
- **Prompt injection filtering** with 9 patterns
- **Content safety filter** for AI responses
- **Startup validation** refuses to start with default secret keys
- **Google token verification** with input validation

---

## Recommendations for Future

1. **Rate limiting** -- Add middleware-level rate limiting (e.g., `slowapi` or Redis-based) to auth endpoints to prevent brute-force attacks
2. **CSP headers** -- Add Content-Security-Policy headers to prevent inline script execution
3. **HTTPS enforcement** -- Ensure all production traffic uses HTTPS
4. **Token rotation** -- Consider rotating refresh tokens on each use (already implemented but worth verifying in production)
5. **Audit logging** -- Log auth events (login, token refresh, logout) for security monitoring
