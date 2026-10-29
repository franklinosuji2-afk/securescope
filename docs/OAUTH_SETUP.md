# Sign in with Google and GitHub

People can sign in (and create an account at the same time) with Google or GitHub. Email and password
sign-in stays available. A provider's button appears only when both of its values are set on the API host,
so nothing changes until you configure one.

## How it works

1. The sign-in page links to `/api/v1/auth/oauth/<provider>/start`. The API sends the browser to the provider
   with a one-time `state`, a PKCE challenge and a short-lived `ss_oauth` cookie that belongs to that browser.
2. The provider sends the browser back to `/api/v1/auth/oauth/<provider>/callback`. The API accepts it only if
   the state is unused, under ten minutes old, issued for that provider and for that same browser.
3. The API exchanges the code with the provider server to server (using the client secret and the PKCE
   verifier) and reads the profile with the access token. Nothing about the person is taken from the browser.
4. Account rules, in this order:
   - A sign-in the API has seen before goes to the same account.
   - Otherwise the provider must report a **verified** email address, or the sign-in is refused.
   - If an account with that email exists and its email was confirmed, the sign-in is linked to it.
   - If it exists but its email was **never confirmed**, its password is removed and its sessions are ended
     before linking, so someone who registered another person's address in advance cannot get into the real
     owner's account. The real owner can set a password again with "Forgot password".
   - If no account exists, one is created with a workspace the person owns, with the email marked confirmed
     and no password.
5. The usual session and CSRF cookies are set and the browser lands on the Overview.

Only the verified email address and the provider's account ID are stored. The scopes asked for are
`openid email` (Google) and `user:email` (GitHub). Failures send the browser back to the sign-in page with a
short reason; the code, the token and the provider's own message are never passed on or logged.

## Environment variables (API host, for example Render)

| Variable | Secret |
|---|---|
| `SECURESCOPE_OAUTH_GOOGLE_CLIENT_ID` | no |
| `SECURESCOPE_OAUTH_GOOGLE_CLIENT_SECRET` | **yes** |
| `SECURESCOPE_OAUTH_GITHUB_CLIENT_ID` | no |
| `SECURESCOPE_OAUTH_GITHUB_CLIENT_SECRET` | **yes** |
| `SECURESCOPE_PUBLIC_BASE_URL` | no. Must be the public address of the site, for example `https://getsecurescope.com` (it is used to build the redirect URI and to send the browser back) |

Set the secrets only in the host's environment. Never put them in the repository, the frontend or a chat.
A provider with only an id or only a secret stays switched off and the API logs a warning that names the provider (never a value).

## Redirect (callback) URIs to register

- Google: `https://getsecurescope.com/api/v1/auth/oauth/google/callback`
- GitHub: `https://getsecurescope.com/api/v1/auth/oauth/github/callback`

They must match exactly, including `https` and no trailing slash. The Cloudflare Worker already forwards
`/api/*` (with redirects and cookies) to the API, so no Worker change is needed.

## Google

1. Google Cloud Console: create a project, then **APIs & Services, OAuth consent screen**.
2. User type **External**. App name `SecureScope`, support email `support@getsecurescope.com`, developer
   contact the same. App home page `https://getsecurescope.com`, privacy policy
   `https://getsecurescope.com/#/privacy`, terms `https://getsecurescope.com/#/terms`. Authorized domain
   `getsecurescope.com`.
3. Scopes: only `openid`, `email`. These are not sensitive, so Google's app verification is not required.
4. **Credentials, Create credentials, OAuth client ID**, type **Web application**, authorized redirect URI as
   above. Copy the client ID and secret into the host environment.
5. While the consent screen is in **Testing**, only listed test users can sign in. Publish it to **In
   production** before inviting anyone else.
6. The Impressum currently withholds the postal address and needs a compliant address solution before you publish the consent screen: Google's consent screen links to the legal pages.

## GitHub

1. GitHub, **Settings, Developer settings, OAuth Apps, New OAuth App**.
2. Application name `SecureScope`, homepage `https://getsecurescope.com`, authorization callback URL as
   above.
3. Generate a client secret. Copy the client ID and secret into the host environment.

## Checking it works

1. Redeploy the API after setting the variables. `GET /api/v1/auth/providers` should list the provider.
2. Open the sign-in page: the buttons appear. Sign in with a new account, then with an existing one.
3. Platform Health and the audit log show the events `user.registered`, `auth.oauth.login`,
   `auth.oauth.linked` and `auth.oauth.failed`.
4. To switch a provider off, remove its two variables.

## Limitations

- Only Google and GitHub. There is no Microsoft or Apple sign-in.
- A sign-in cannot be unlinked from the account screen yet.
- GitHub is trusted only for its primary, verified email address. An account with no verified primary email is
  refused.
- If a person changes the email address at the provider, the link follows the provider's account ID, not the
  address.
- A person who signs in this way has no password until they use "Forgot password".
- Sign-in attempts are rate limited per client address (`SECURESCOPE_OAUTH_ATTEMPTS_PER_IP_PER_15MIN`).
