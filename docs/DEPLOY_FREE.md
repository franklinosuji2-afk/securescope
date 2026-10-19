# Free public deployment (web and phone)

Cost: $0 on free tiers. Free-tier terms change, so check each provider's current limits when you sign up.

```
Phone / browser ──HTTPS──> Cloudflare Pages (static app + /api proxy Function)
                                   │  adds X-Proxy-Secret and the visitor's address
                                   ▼
                           Render free web service (Docker, FastAPI)
                                   │  TLS
                                   ▼
                              Neon free Postgres
Email: Brevo (or Resend) HTTPS API, called by the backend
```

The browser only ever talks to one origin (your Pages domain), so cookies, CSRF and CORS behave exactly as on localhost.

## 0. Secrets you will create

Never commit these and never paste them into chat. Each lives only in the provider's dashboard.

| Name | What | Where it is set |
| --- | --- | --- |
| `PROXY_SECRET` / `SECURESCOPE_TRUSTED_PROXY_SECRET` | One long random string, the same in both places (for example 48 random characters from a password manager). | Cloudflare Pages and Render |
| Neon connection string | `postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require` | Render |
| Mail API key | From Brevo or Resend | Render |

## 1. Neon (database)

1. Create a project and database. Choose the region closest to Render's (Frankfurt if available).
2. Copy the connection string. Change the scheme to `postgresql+psycopg://` and keep `?sslmode=require`.
3. Migrations run automatically every time the API starts, so there is nothing to run by hand.

## 2. Email provider

Brevo: create an account, verify one sender address (no domain needed), create an API key. Resend: only sends to arbitrary recipients from a domain you verified.

Set `SECURESCOPE_MAIL_PROVIDER` (`brevo` or `resend`), `SECURESCOPE_MAIL_API_KEY` and `SECURESCOPE_MAIL_FROM_EMAIL` (the verified sender). If the provider is down or the key is wrong, sign-ups still work and the log shows `mail send failed` with the status code (never the message or key).

## 3. Render (API)

1. New > Blueprint, pick this repository. `render.yaml` defines the service.
2. Fill in the variables marked `sync: false`:
   - `SECURESCOPE_DATABASE_URL`: the Neon string from step 1.
   - `SECURESCOPE_PUBLIC_BASE_URL`: `https://YOUR-SITE.pages.dev` (email links point here).
   - `SECURESCOPE_CORS_ORIGINS`: `["https://YOUR-SITE.pages.dev"]` (a JSON list).
   - `SECURESCOPE_TRUSTED_PROXY_SECRET`: the shared secret.
   - the three mail variables.
3. Deploy. `https://YOUR-API.onrender.com/api/v1/ready` should answer `200`.

Free instances sleep after 15 minutes without traffic and take about a minute to wake. Rate-limit counters and running scans do not survive a sleep or restart (a scan left running is marked failed on the next start).

## 4. Cloudflare Pages (app and proxy)

1. Create a Pages project from this repository. Root directory: `frontend`. Build command: `npm run build`. Output: `dist`.
2. Settings > Variables and Secrets (Production), as **secrets**:
   - `BACKEND_URL`: `https://YOUR-API.onrender.com` (no trailing slash)
   - `PROXY_SECRET`: the shared secret.
3. Redeploy once after adding them. `frontend/functions/api/[[path]].js` forwards `/api/*` to Render, replaces any visitor-supplied proxy headers, and passes the visitor's real address using `CF-Connecting-IP`.
4. `frontend/public/_headers` gives the site the same security headers as the local nginx setup.

## 5. Check it

1. Open `https://YOUR-SITE.pages.dev`, register, and confirm the verification email arrives.
2. Add and verify one of your own domains, then run a scan.
3. Try registering with a wrong password five times: you should be rate limited, and only you (not every visitor).
4. On Android (Chrome) or iPhone (Safari) open the site and use "Install app" / "Add to Home Screen".

## Before you share the link

- Add an **Impressum** and a privacy notice (required for a public site run from Germany that collects email addresses). `docs/PRIVACY.md` is a starting point; the legal details are yours to provide and to have checked.
- Decide whether sign-ups stay open. Per-visitor limits help, but open registration invites junk accounts.
- Know the limits: single instance, in-memory rate limits, no backups beyond what Neon provides, scans only against domains the user has verified.

## Why the proxy secret

The Render address is public. If the backend believed an `X-Forwarded-For` header, anyone calling it directly could pick their own address and dodge every limit. Instead the backend uses a visitor address only when the request also carries the shared secret, which only the Pages Function knows. Anything else falls back to the connection's own address.
