# M0 — eigenaar-checklist

Acties die alleen de eigenaar kan uitvoeren (dashboard-toegang, geen
repo-toegang) — niet iets wat een agent voor je kan doen. Elke sectie is
zelfstandig; voer uit wanneer relevant.

## Cloudflare rate rule — `/api/auth/*` (WS-E.4)

De backend rate-limit (`core/ratelimit.py`, `routers/auth.py`) draait
in-process en is **per uvicorn-worker** (productie draait 4 workers) —
dus geen exacte, cross-worker, cross-restart harde grens. De Cloudflare
edge is dat wel: dit is de eigenlijke backstop tegen brute-force/
credential-stuffing tegen `/api/auth/*`, vóór het verkeer de VPS
bereikt.

Aanmaken in het Cloudflare dashboard voor `gsprecruitment.nl` →
**Security → WAF → Rate limiting rules** → *Create rule*:

| Veld | Waarde |
|---|---|
| Rule name | `auth-rate-limit` |
| If incoming requests match | `URI Path` `contains` `/api/auth/` |
| Rate | **30 requests per 10 seconds** |
| Counting characteristic | Per IP address (Cloudflare's own edge IP, not a spoofable header — same reasoning as `CF-Connecting-IP` in `core/ratelimit.py`) |
| Then | Block |
| Duration of block | **1 minute** |

Volgorde: deze regel hoort vóór eventuele algemene "allow known bots"-
uitzonderingen te staan, maar hoeft niet vóór de WAF managed rules — hij
matcht alleen op path, dus interfereert niet met andere routes.

**Waarom niet in code:** dit is een edge/CDN-instelling buiten de repo —
er is geen Cloudflare API-token in deze omgeving beschikbaar, en het
hoort sowieso bij infra die de eigenaar zelf beheert (Cloudflare
dashboard-toegang), niet bij een backend-deploy.

**Verifiëren na aanmaken:**
```bash
for i in $(seq 1 35); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "User-Agent: gsp-ops" \
    -X POST https://api.gsprecruitment.nl/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"doesnotexist@example.com","password":"wrong"}'
done | sort | uniq -c
```
Verwacht: de eerste ~30 responses `401` (backend-niveau, geen account),
daarna `429`/`403` (Cloudflare's block) voor de rest van die minuut.
