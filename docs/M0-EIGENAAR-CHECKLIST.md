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

## Firewall: alleen Cloudflare mag origin bereiken (WS-E.4, security-audit)

`core/ratelimit.py`'s `get_client_ip` vertrouwt de `CF-Connecting-IP`-
header als eerste keus voor de rate-limit-key — maar die header is alleen
betrouwbaar zolang elk request dat de VPS bereikt daadwerkelijk via
Cloudflare's edge liep. Zonder deze stap kan iedereen rechtstreeks naar
`api.gsprecruitment.nl`'s onderliggende IP verbinden (poort 443
overslaat Cloudflare volledig) en zelf een willekeurige
`CF-Connecting-IP`-header meesturen — daarmee is zowel de per-IP
rate-limit-key als de Cloudflare rate rule hierboven te omzeilen.

Kies één van deze twee (beide zijn owner/infra-acties, geen code-deploy):

**Optie A — firewall op poort 443 naar Cloudflare's IP-ranges** (voorkeur,
sluit het probleem echt af):
1. Haal de actuele lijst op: https://www.cloudflare.com/ips/ (IPv4 +
   IPv6) — dezelfde ranges als de default-lijst in
   `core/ratelimit.py`'s `_DEFAULT_TRUSTED_PROXY_CIDRS`, maar controleer
   ze; Cloudflare breidt ze af en toe uit.
2. Op de Hetzner VPS (`ufw`, of het cloud firewall in de Hetzner
   console): sta poort 443/tcp alleen toe vanaf die ranges, blokkeer
   verder al het andere verkeer naar 443. Laat 22/SSH ongemoeid (eigen
   regels).
3. Test na toepassen: een `curl` rechtstreeks naar het VPS-IP (niet via
   `gsprecruitment.nl`) op 443 moet nu weigeren/timeouten; via
   `https://api.gsprecruitment.nl` moet alles gewoon blijven werken.

**Optie B — Caddy `trusted_proxies` + header strippen** (als firewalling
niet haalbaar is, bv. andere services op dezelfde host die wel direct
bereikbaar moeten zijn):
1. In de Caddyfile: zet `trusted_proxies` op Cloudflare's IP-ranges voor
   de site-block van `api.gsprecruitment.nl`, zodat Caddy zelf al
   Cloudflare-only redeneert voor X-Forwarded-For.
2. Voeg een `header_down -CF-Connecting-IP` (of gelijkwaardig: alleen
   doorlaten als de binnenkomende request-peer in de Cloudflare-ranges
   zit) toe, zodat een direct-to-origin request geen eigen
   `CF-Connecting-IP` kan meesmokkelen die de backend voor
   Cloudflare-afkomstig aanziet.

Zie ook `core/ratelimit.py`'s moduledocstring: productie draait uvicorn
met `--proxy-headers --forwarded-allow-ips=*` achter Caddy, dus
`request.client.host` is daar al de meest-linkse X-Forwarded-For-hop —
de trusted-proxy-tak in `get_client_ip` is voor die praktijk-situatie dan
grotendeels overbodig (maar blijft de juiste fallback voor elke opstelling
zonder die uvicorn-vlag).

## Branch protection op `main` (WS-E.9)

GitHub-instelling, geen code-change — moet handmatig door de eigenaar
worden aangezet (Settings → Branches → Add branch protection rule → main
in de GitHub-repo).

1. **Require status checks to pass before merging** aanzetten, en deze
   exacte job-namen uit `.github/workflows/ci.yml` toevoegen als required
   checks:
   - `Backend (Python)` (job `backend`)
   - `Mobile (Expo/TypeScript)` (job `mobile`)
   - `Backend dependency audit (pip-audit)` (job `pip-audit`)
   - `Lockfile matches requirements.txt` (job `lock-consistency`)
   - `Secret scan (gitleaks)` (job `gitleaks`)
   - `Website (static checks + CSP)` (job `web`)

   (De namen moeten letterlijk overeenkomen met het `name:` veld van elke
   job in `ci.yml` — als een job daar ooit hernoemd wordt, moet deze lijst
   in dezelfde PR mee-updaten, anders "verdwijnt" de check stilletjes uit
   de required-lijst zonder dat GitHub dat meldt.)

2. **Require branches to be up to date before merging** aanzetten — een PR
   moet main's laatste commit al gemerged/gerebaset hebben voordat hij
   gemerged mag worden, zodat een check nooit tegen een verouderde
   combinatie van bestanden groen slaat.

3. Optioneel maar aan te raden: **Require a pull request before merging**
   (voorkomt een directe push naar `main`, ook door de eigenaar zelf) en
   **Do not allow bypassing the above settings** (anders geldt de regel
   niet voor repo-admins, wat de eigenaar zelf is).

`deploy.yml` draait apart op elke push naar `main` en is zelf geen
required check hier — die job faalt/rolt terug op zijn eigen
health-check (zie boven in dit bestand), branch protection dekt de
*merge*-poort, niet de deploy zelf.
