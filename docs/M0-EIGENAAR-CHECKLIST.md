# M0 — checklist voor de eigenaar (week 1)

Hoort bij MASTERPLAN-2026.md, WS-E.1. Dit zijn de handelingen die alleen een mens met VPS-, GitHub- en Cloudflare-toegang kan doen. Voer ze uit in deze volgorde; vink af in dit bestand of meld het in de sessie. Zet nooit een secret in git, in een chat of in een issue.

## 1. Handmatige backup (WS-E.5a) — vóór alle andere stappen

Op de VPS, in de map met `docker-compose.yml` van talent-os:

```bash
# 1a. Databasedump, versleuteld met een wachtwoord dat je alleen lokaal bewaart
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner \
  | gpg --symmetric --cipher-algo AES256 -o "gsp-db-$(date +%F).sql.gpg"

# 1b. Alleen het schema (voor WS-C.1, mag onversleuteld — bevat geen data)
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema-only --no-owner \
  > "gsp-schema-$(date +%F).sql"

# 1c. CV-bestanden die nog lokaal staan (tot R2 actief is)
docker compose cp backend:/app/uploads "./uploads-$(date +%F)" 2>/dev/null || echo "geen lokale uploads-map"

# 1d. init_db.sql als dat bestand op de VPS bestaat
ls -la talent-os/scripts/init_db.sql 2>/dev/null || echo "init_db.sql ontbreekt op de VPS"
```

Zet `gsp-db-*.sql.gpg` en de uploads-kopie **buiten de VPS** (eigen laptop plus een tweede plek). Lever `gsp-schema-*.sql` aan in de sessie (bestand uploaden); daar bouwt WS-C.1 de baseline-migratie van.

## 2. Datalek-beoordeling (WS-E.1b) — dezelfde dag

Doel: vaststellen of de vier lekken uit §2 al zijn misbruikt. Alleen lezen.

```sql
-- admins en hoe ze zijn ontstaan
SELECT id, email, role, is_verified, created_at FROM users WHERE role = 'admin' AND deleted_at IS NULL ORDER BY created_at;
-- zelfgeregistreerde client-accounts
SELECT id, email, created_at FROM users WHERE role = 'client' AND deleted_at IS NULL ORDER BY created_at;
-- team-uitnodigingen (wie heeft wie aangemaakt)
SELECT * FROM audit_log WHERE action ILIKE '%team%' OR action ILIKE '%invite%' ORDER BY created_at DESC LIMIT 100;
```

Access-logs (Caddy op de VPS en/of Cloudflare → Security → Events / Logs) filteren op:
`/api/v1/client/candidates`, `/api/v1/client/candidates/`, `/api/v1/client/team` — sinds de deploy van die routes. Client-reads staan niet in `audit_log`; de access-logs zijn het enige bewijs.

Beslissingen die hieruit volgen (vastleggen in `docs/COMPLIANCE-REGISTER.md` zodra dat bestaat, tot dan in dit bestand):
- Onbekende admin-accounts of client-reads op kandidaten gevonden → melding bij de Autoriteit Persoonsgegevens binnen 72 uur na ontdekking (Art. 33) en beoordeling of betrokkenen geïnformeerd moeten worden (Art. 34).
- `website/logo.pdf` (factuur van een derde met IBAN en adressen) is publiek geweest sinds 2026-07-07: de derde informeren is redelijk; noteer datum en besluit.

## 3. Secrets roteren (§5.6) — direct ná merge van de PR voor WS-C.2

Volgorde:
1. `JWT_SECRET` én het admin-wachtwoord (maakt alle bestaande admin-tokens ongeldig; iedereen logt opnieuw in).
2. `API_KEY` en `WEBHOOK_SECRET` — één keer; **binnen hetzelfde uur** de zeven routines bijwerken die de API-key gebruiken (gsp-morning-brief, gsp-draft-qa, gsp-match-and-draft, gsp-client-leads, gsp-candidate-scout, gsp-blog-weekly, gsp-weekly-review): meld in de sessie dat de nieuwe waarde in de VPS-`.env` staat, dan worden de routine-prompts aangepast zonder de waarde in de chat te zetten.
3. OpenRouter-, Apollo- en Google-tokens; Telegram-bottoken (die stond in een oude routine-prompt).
4. Nieuwe waarden alleen in `talent-os/.env` op de VPS en in GitHub Secrets. Daarna `docker compose up -d --force-recreate backend`.

Bevestig ook: is de GitHub-repo publiek? Zo ja, dan wordt na merge van WS-A.1 de git-geschiedenis herschreven zodat `logo.pdf` ook uit oude commits verdwijnt.

## 4. Apollo-sync uit

WS-C.3a zet de standaard op uit. Controleer na deploy dat `APOLLO_SYNC_ENABLED` niet op `true` staat in de VPS-`.env`.

## 5. App (WS-D.0)

Eén vraag: is de Expo-app ooit gedistribueerd (TestFlight, APK, Expo Go-link)? Ja/nee bepaalt of de app-fixes nu of pas na twee plaatsingen gebeuren.

## 6. Na merge van elke M0-PR

- WS-A.1: Cloudflare → Caching → Purge everything; daarna `curl -sI -A gsp-ops https://gsprecruitment.nl/logo.pdf` moet 404 geven.
- WS-A.9b: `curl -sI -A gsp-ops https://gsprecruitment.nl/ | grep -iE "strict|content-security|x-frame|nosniff|referrer|permissions"` toont de headers; open admin, kandidaten- en klantportal met devtools open en meld CSP-meldingen in de sessie.
- WS-C.2 / C.3a: deploy loopt via de bestaande workflow; `curl -s -A gsp-ops https://api.gsprecruitment.nl/health` toont alleen status/version/database.
