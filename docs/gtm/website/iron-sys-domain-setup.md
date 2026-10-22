# iron-sys.com → company website (bunny.net)

Set up 2026-10-22 (Jira PP-19, plan G-11). How the company domain reaches the `iron-systems-website` container, and how to
repeat it for another app.

## Current setup

| Piece | Where | Value |
|---|---|---|
| Website container | bunny.net Magic Containers, app `iron-systems-website` (`24KqEc9MRrgR22B`) | image `MooRaa86/iron-systems-website:latest`, container port 80 |
| bunny endpoint | `endpoint-0` (CDN) | `mc-f33qwbh3f1.bunny.run` |
| Custom hostname | bunny → app → Endpoints → `endpoint-0` | `www.iron-sys.com`, SSL verified (Let's Encrypt, auto-renewed by bunny) |
| `www` DNS record | GoDaddy → `iron-sys.com` → DNS Records | `CNAME www → mc-f33qwbh3f1.b-cdn.net`, TTL 1 hour (was `CNAME www → iron-sys.com.`) |
| Bare domain | GoDaddy → `iron-sys.com` → DNS → Forwarding | `iron-sys.com` → `https://www.iron-sys.com`, permanent (301), no masking |

DNS for `iron-sys.com` stays at GoDaddy (nameservers `ns75`/`ns76.domaincontrol.com`). Every other
record (Zoho MX, mail, `procurepilot`, `procurepilot-api`, `form-craft`, …) was left unchanged.

### Why `www` + forwarding, not the bare domain

GoDaddy cannot put a CNAME on the bare domain (`@`), and bunny expects a CNAME. An A record to the
bunny IP would work today but breaks silently if bunny changes that IP. So the site lives on `www`,
and GoDaddy's forwarding service (its own A records, `3.33.251.168` / `15.197.225.128` since HTTPS forwarding went live; managed by GoDaddy, do not edit) redirects the
bare domain there.

## Verified 2026-10-22

- `https://www.iron-sys.com` → 200, certificate `CN=www.iron-sys.com`, issuer Let's Encrypt, expires 2027-01-20.
- `https://www.iron-sys.com` and `https://mc-f33qwbh3f1.bunny.run` return byte-identical HTML (same
  SHA-256, same bunny pull zone `6848635`, title "Iron Systems | Powering Businesses with
  Intelligent Technologies"), so `www` is served by the container itself.
- `http://iron-sys.com` → 301 → `https://www.iron-sys.com/`.
- `https://iron-sys.com` → 301 → `https://www.iron-sys.com/` (verified 2026-10-23 01:57). Certificate
  `CN=iron-sys.com`, issued by GoDaddy, expires 2027-05-08. It took GoDaddy about 6 hours to start
  serving HTTPS: until then, port 443 on the forwarding IPs timed out with no certificate. When it
  went live, the forwarding A records changed from `3.33.152.147` / `15.197.142.173`.

## Linking another bunny container to a subdomain

1. **bunny.net**: app → **Endpoints** → **Add a Custom Hostname** → enter e.g. `app.iron-sys.com`.
   The dialog shows the CNAME value (`mc-xxxxxxxx.b-cdn.net`). Leave it open.
2. **GoDaddy**: My Domains → `iron-sys.com` → **DNS** → **DNS Records** → **Add New Record**:
   type `CNAME`, name `app`, value `mc-xxxxxxxx.b-cdn.net`, TTL 1 hour. Edit instead if the name
   already exists.
3. Wait until it resolves publicly: `dig +short CNAME app.iron-sys.com @1.1.1.1` (usually minutes).
4. **bunny.net**: click **Verify & Activate SSL**. It reports "SSL Verification was successful".
5. Check: `curl -sSv https://app.iron-sys.com/ -o /dev/null 2>&1 | grep -E 'subject:|issuer:'`.

If the local machine still cannot resolve the name, it is caching the old answer: test with
`curl --resolve app.iron-sys.com:443:<ip from dig @1.1.1.1>` or flush the local DNS cache.
