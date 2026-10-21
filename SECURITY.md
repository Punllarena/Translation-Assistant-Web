# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through GitHub's
[private vulnerability reporting](https://github.com/Punllarena/Translation-Assistant-Web/security/advisories/new)
with:

- what is affected (endpoint, page, or file),
- steps to reproduce, and
- the impact you expect.

Only the latest commit on `main` receives fixes.

## Security model

- **Accounts** are invite-only; the setup wizard creates the first admin while no users exist.
- **Sessions** are opaque random tokens stored hashed; the cookie is `Secure` and `HttpOnly`.
- **Passwords** are hashed with Argon2. Login attempts are rate-limited per client address, per
  submitted login, and per account.
- **Stored credentials** (DeepL and WordPress keys) are encrypted with `TA_SECRET_KEY`.
- **Tenancy.** Another user's rows answer 404, so their existence is not disclosed.
- **Outbound requests.** User-supplied LibreTranslate, Ollama and WordPress URLs that resolve to a
  private, loopback, link-local or CGNAT address are refused unless the operator allows them
  (`TA_MT_ALLOW_PRIVATE_URLS`, `TA_WP_ALLOW_PRIVATE_URLS`). WordPress redirects are never followed.
  Syosetu fetches are limited to `*.syosetu.com`.
- **Uploads** are size-capped at Caddy and in the API, and file types are sniffed by magic bytes.

## Known limitations

- **Fresh installs are open.** Until the first account exists, anyone who reaches the site can create
  the admin. Finish setup before exposing the server; see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
- **DNS rebinding.** The private-address guard checks DNS when a request is prepared and does not pin
  the result, so a host whose DNS changes between the check and the call can bypass it. Keep this in
  mind before giving untrusted users access.
- **Login limiter behind Cloudflare Tunnel.** Every request arrives from `cloudflared`, so the
  per-address limiter is effectively global: repeated failures lock out everyone for the window. An
  opt-in trust of `CF-Connecting-IP` is planned.
- **Losing `TA_SECRET_KEY`** makes stored credentials unreadable. Back it up with the database.
