# Werkverdeling tussen agents

Doel: het bedrijf draaien vanaf een telefoon, met Hermes als orkestrator op de eigen machine (Omarchy), zonder de Claude-desktop-app op Windows, en met Claude Code alleen voor het werk dat het echt nodig heeft. Dit document legt vast wie wat doet, hoe ze met elkaar praten, en wat er nooit naar een goedkoper model mag.

Uitgangspunten: Hermes kan cron-taken draaien, shellcommando's en HTTP-aanroepen doen, met Telegram praten, en heeft meerdere profielen met elk een eigen model en eigen instructies. Agent Zero is een los product met een eigen Docker-sandbox, browser- en desktopbesturing, en is als MCP-server aan Hermes gekoppeld; Hermes roept het aan als gereedschap. Codex is de tweede coder. Claude Code is de poortwachter.

## 1. Eén bus: GitHub plus Telegram

Alle agents praten via twee kanalen die er al zijn en die vanaf een telefoon werken.

- **GitHub issues zijn de werkvoorraad.** Elke taak is een issue met één routeringslabel: `hermes`, `agent0`, `codex` of `claude`. Wie het label draagt, doet het werk en rapporteert in het issue. Een PR sluit het issue ("Closes #n"). Zonder label gebeurt er niets; dat is de rem.
- **Telegram is het rapportagekanaal.** Korte meldingen, nooit persoonsgegevens (dat is nu al de regel voor de routines). Vanaf de telefoon geef je opdrachten aan Hermes in Telegram; Hermes maakt er issues van met het juiste label.
- **De repo is de enige bron van waarheid.** `CLAUDE.md` (huisregels), `SITE-DESIGN-SPEC.md`, `docs/VERWERKINGSREGISTER.md`, `docs/SOURCING-SOP.md`. Elk profiel krijgt dezelfde huisregels in zijn systeeminstructie; een goedkoper model mag ze niet minder streng lezen.

Wat hierdoor niet meer nodig is: de Claude-desktop-app als doorgeefluik, Cowork als taakuitvoerder (Agent Zero neemt dat over), en een Claude-sessie die elke vier uur wakker wordt om te kijken of er werk is.

## 2. Rollen

### Hermes, hoofdprofiel: orkestrator

Het enige profiel dat opdrachten van de eigenaar aanneemt. Verdeelt, plant, bewaakt, rapporteert. Schrijft zelf geen code.

- Intake vanaf Telegram: opdracht naar issue met label, prioriteit en een korte definitie van klaar.
- Routing volgens tabel §3. Twijfel is `claude`, nooit `agent0`.
- Cron: de zeven routines uit `CLAUDE.md` (morning brief, draft-QA, match-and-draft, client leads, candidate scout, blog weekly, weekly review). Die draaien nu als Claude Routines; ze verhuizen naar Hermes-cron met een goedkoper model, één voor één, na een week parallel draaien.
- Bewaking: CI-status per PR, deploystatus na een merge, `GET /health` van de API, de logregels van de droogloopjobs (`accounts_due` uit de slapend-accountjob). Meldt afwijkingen op Telegram.
- Eigenaarslijsten bijhouden: de checklists in `docs/EMAIL-SETUP.md` §9, de "na de merge"-secties van PR's. Hermes herinnert, de eigenaar doet.

### Agent Zero (via MCP in Hermes): de handen op de machine, de vervanger van Cowork

Alles wat een desktop, een browser of het lokale bestandssysteem nodig heeft. Dit is het werk dat Cowork deed en dat vanaf een telefoon niet kan.

- Beheerconsoles die geen API hebben of waar een klik veiliger is dan een script: de WAF-uitzondering en DNS-records in Cloudflare (`docs/EMAIL-SETUP.md` §8 en de DNS-stappen), de OAuth-client en het toestemmingsscherm in Google Cloud Console (`docs/GOOGLE-SIGNIN-SETUP.md`), de sitemap opnieuw indienen in Search Console, Play Console-stappen uit `docs/APP-RELEASE.md`.
- Controles in een echte browser: de eigenaarslijsten uit PR-teksten (zijmenu op mobiel, cookiebanner boven de WhatsApp-pil, footer-mailto, de dienstenladder op 768px), met screenshots terug in het issue.
- Lokale bestanden en documenten: contracten en PDF's lezen en samenvatten, exports opslaan, de uploads-map beheren.
- Data-operaties in zijn sandbox met de `X-API-Key`: vacatures seeden (`scripts/seed_pool_vacancies.py`, dry-run eerst, uitvoer in het issue), `GET /api/public/jobs` controleren, `GET /health` na een deploy.
- Kleine repo-taken die geen redenering vragen: een branch maken, een script draaien, een checklist afvinken.

Agent Zero krijgt geen admin-JWT, geen databasetoegang tot productie en geen wachtwoorden in zijn prompt; consoles waar het inlogt gebruiken een eigen, beperkt account waar dat kan, en elke handeling in een beheerconsole eindigt met een screenshot in het issue zodat de eigenaar het kan zien. Voor code-review en codewijzigingen is Agent Zero niet de eerste keus; dat is Codex.

### Codex: werker voor code met laag risico

Mechanisch en middelgroot codewerk op een branch, met PR. Nooit merge, nooit deploy, nooit iets onder §4.

- Kopij en documentatie: meta-omschrijvingen, blogteksten volgens de SOP, registerteksten die de code al doet, vertalingen van Engelse chrome in het adminpaneel.
- Tests schrijven voor bestaande gedragingen, afhankelijkheden bijwerken (Dependabot-PR's beoordelen), CI-scripts die rood staan op iets triviaals.
- Frontend- en backendwijzigingen zonder persoonsgegevens: een kolom in een adminlijst, een label, een filter, een lege staat, een sorteerknop op een route die `sort` al kent; adminsecties die alleen bestaande routes tonen (plaatsingen, users, health, pipeline-tab), portaalschermen, blogindex.
- Eerste review op PR's (`@codex`), vóór Claude erbij komt.

Codex werkt met de repo-scripts als vangrail: `check_api_contract.py`, `generate_openapi_snapshot.py --check`, `xss_static_check.py`, `css_tokens_check.py`, `admin_ui_check.py`, de testsuite tegen een verse Postgres. Groen is de toegangseis voor een PR; de scripts vervangen daarmee een deel van de menselijke en Claude-review.

### Hermes, profiel "claude code": de aanroep van Claude

Geen eigen rol, maar de manier waarop Hermes Claude Code start zonder desktop-app. Twee mechanismen, kies er één als standaard:

1. **Headless op Omarchy.** `claude -p "<opdracht>" --allowedTools ...` als subprocess, in een checkout van de repo, met het abonnement. Goedkoop in opzet, draait op de eigen machine, verbruikt abonnementsquota. Geschikt voor alles wat binnen één sessie past.
2. **Claude Code GitHub Action.** `anthropics/claude-code-action` in `.github/workflows/`, getriggerd op het label `claude` of een `@claude`-comment. Draait in GitHub, betaald per token via een API-sleutel, onafhankelijk van welke machine aanstaat. Geschikt als de eigen machine uit kan staan en als audittrail (alles staat in het issue).

Aanbeveling: mechanisme 2 als standaard voor `claude`-issues, mechanisme 1 voor interactief werk vanaf de telefoon via Hermes. Het bestaande `gsp-taskdesk`-routine (elke vier uur wakker, meestal niets te doen) vervalt zodra een van beide staat.

### Claude Code: alleen het kritieke

Claude doet wat een fout duur maakt of wat een reviewketen met bewijs vereist:

- Alles onder §4 (auth, persoonsgegevens, toestemming, bewaartermijnen, outreach, betalingen, migraties die data raken).
- Architectuur en specs: nieuwe secties in `SITE-DESIGN-SPEC.md`, het verwerkingsregister, wijzigingen aan `deploy.yml` of `docker-compose.yml`.
- De poortwachtersrollen uit `.claude/agents/`: `security-auditor` vóór elke release die auth of persoonsgegevens raakt, `chief-of-staff` als laatste interne verdict op release-PR's, `design-reviewer` op visuele wijzigingen aan de publieke site.
- Incidenten: een 500 op productie, een mislukte migratie, een AVG-verzoek dat vastloopt.
- Werk dat Codex of Agent Zero twee keer heeft laten liggen.

Wat Claude niet meer doet: pollen op issues, routines draaien, kopij, seeds, consoleklikken, browsercontroles, CI-groen-maken, en reviews van werk dat de scripts al afdekken.

## 3. Routeringstabel

| Soort werk | Label | Reviewer | Chief-of-staff |
|---|---|---|---|
| Beheerconsoles (Cloudflare WAF en DNS, Google Cloud Console, Search Console, Play Console) | `agent0` | screenshot in het issue, eigenaar kijkt | nee |
| Browsercontroles van eigenaarslijsten, seeds, sitemap, data-ops via API, lokale documenten | `agent0` | screenshot of uitvoer in het issue | nee |
| Kopij, docs, vertalingen, meta | `codex` | scripts | nee |
| Dependabot, CI-fix, tests voor bestaand gedrag | `codex` | scripts | nee |
| Adminscherm of portaalscherm zonder persoonsgegevens (plaatsingen, users, health, pipeline-weergave, analytics) | `codex` | scripts, Claude `code-reviewer` bij de PR | nee |
| Publieke site, visueel | `codex` | Claude `design-reviewer` bij de PR, Agent Zero voor de browsercontrole | alleen bij een hele pagina |
| Adminscherm met persoonsgegevens, toestemming, bewaartermijnen, AVG-wissen, referral-intake, suppressielijst | `claude` | `security-auditor` + `code-reviewer` | ja |
| Backend: auth, e-mailverzending, matching, outreach, migraties | `claude` | `security-auditor` + `code-reviewer` | ja |
| Spec, register, SOP, infra | `claude` | `code-reviewer` | ja |
| Routines (dagelijks/wekelijks) | Hermes-cron | geen | nee |
| Bewaking en rapportage | Hermes | geen | nee |

Voor WS5 betekent dit concreet: de goedkeuringslijst bewaartermijnen, toestemmingen en referral-intake, AVG-wissen en suppressielijst gaan naar `claude`; plaatsingen, pipeline-tab, users/unlock/health/prospects, de job-alertschakelaar in het kandidatenportaal en het klantportaal (kanban, analytics, contacten, teamtabel) gaan naar `codex` met een Claude-codereview bij de PR, en Agent Zero doet de browsercontrole op de live site na elke merge.

## 4. Wat nooit naar een goedkoper model gaat

Deze regels staan in `CLAUDE.md` en gelden voor elk profiel; hier staat welke dus alleen door Claude met de volledige keten worden aangeraakt.

- Alles wat schrijft naar `candidates`, `users`, `talentpool_optin_requests`, `suppression_list`, `retention_review_*`, `job_alert_sends`, of leest uit een art. 15-export.
- Alles wat een e-mail verstuurt. Outreach blijft draft-only: geen enkel profiel mag een verzendpad toevoegen.
- Auth, MFA, tokens, API-sleutels, de WAF-regel, DNS.
- Migraties die bestaande rijen wijzigen (normalisaties, constraints).
- Merge naar main en deploy: dat blijft de eigenaar, met één uitzondering die de eigenaar per sessie expliciet geeft.

Hermes, Agent Zero en Codex krijgen daarom geen admin-JWT en geen databasetoegang tot productie; alleen de `X-API-Key` voor de publieke en kandidaat/vacature-routes, en GitHub-schrijfrechten op branches en issues, niet op main.

## 5. Kan Hermes met de Claude-desktop-app, Cowork of de cloudomgevingen praten?

Kort: niet met de desktop-app of Cowork, wel met Claude Code in de cloud, en dat laatste is genoeg.

- **Claude-desktop-app en Cowork** hebben geen API waar iets van buiten in kan schrijven. De desktop-app kan wel MCP-servers gebruiken, maar dat is de app die naar buiten praat, niet andersom. Cowork is een lokale desktopfunctie; niets kan een Cowork-taak op afstand starten. Conclusie: die twee vervallen in dit model. Het desktopwerk van Cowork (bestanden, browser, consoles) gaat naar Agent Zero, aangestuurd door Hermes via MCP; het denkwerk dat je via Cowork aan Claude gaf, gaat via GitHub-issues met het label `claude`.
- **Claude Code in de cloud** (claude.ai/code) is te bereiken op drie manieren zonder desktop-app: (1) vanaf de telefoon in de browser of de mobiele app, (2) via Routines die op schema of op aanroep een sessie starten, (3) via de GitHub Action, die effectief een Claude Code-run in CI is. Hermes gebruikt 3 als standaard. Binnen een lopende cloudsessie kan Claude zelf nieuwe sessies en Routines aanmaken (dat gebeurt nu ook), dus als Hermes één sessie start, kan die de rest orkestreren.
- **Headless op Omarchy** is de vierde weg: Hermes roept `claude -p` aan als subprocess. Dat is de "profiel 3"-constructie. Werkt zonder cloud, maar alleen als de machine aanstaat.

Wat Hermes dus praktisch doet bij een `claude`-issue: label zetten (Action start), of `claude -p` starten met het issuenummer als opdracht. Terugkoppeling komt als comment in het issue en als PR; Hermes leest die en meldt op Telegram.

## 6. Tokenregels voor Claude

- Eén reviewketen per PR, geschaald naar risico zoals `CLAUDE.md` voorschrijft. Geen tweede ronde omdat een reviewer een testgat vond dat een script had kunnen vangen: voeg dan het script toe en laat Codex het draaien.
- Niet meer dan twee parallelle Claude-agents per sessie tenzij het echt onafhankelijke sporen zijn.
- Geen Claude-agent voor iets dat een screenshot of een consoleklik is: dat is Agent Zero.
- Geen Claude-sessie die polt. `gsp-taskdesk` uit zodra Hermes de issues bewaakt.
- Routines op Hermes, niet op Claude, behalve `gsp-draft-qa` zolang die persoonsgegevens beoordeelt (dan `claude`, wekelijks in plaats van dagelijks, of Hermes met een lokaal model en zonder de gegevens te bewaren).
- Chief-of-staff alleen op release-PR's (auth, persoonsgegevens, hele pagina's, infra). Niet op kopij, docs, seeds, kleine schermen.
- Screenshots en metingen door scripts, niet door een agent die ze beschrijft: `admin_ui_check.py`, `admin_sections_check.py`, de sweep-scripts uit de kaartenronde horen in `scripts/` en draaien in CI.

## 7. Migratiestappen, in volgorde

1. **Labels en werkvoorraad.** Vier labels in GitHub aanmaken. Hermes-orkestrator krijgt: issues lezen en aanmaken, comments, branches en PR's; niet mergen. Eerste week: alleen intake en routing, nog niets uitvoeren.
2. **Agent Zero aan het werk op de openstaande eigenaarslijst.** Seed van de 27 vacatures op productie (dry-run, `--apply`, `GET /api/public/jobs` moet 27 geven), sitemap opnieuw indienen in Search Console, de browsercontroles uit PR #93 op de live site met screenshots, en de consolestappen uit `docs/EMAIL-SETUP.md` §8 en `docs/GOOGLE-SIGNIN-SETUP.md` (de WAF-uitzondering en DNS pas na jouw akkoord per stap, met screenshot vooraf en achteraf). Dit is de proef of Agent Zero in beheerconsoles betrouwbaar genoeg is.
   **Codex op de eerste codetaken:** Engelse chrome in het adminpaneel vertalen, de vijf ontbrekende tokens in `theme.css`, `.text-uppercase` loskoppelen van mono (§7.9).
3. **Claude-aanroep zonder desktop.** GitHub Action op het label `claude` inrichten (API-sleutel als repo-secret, nooit in code), één proefissue. Daarna `gsp-taskdesk` uitzetten.
4. **Routines verhuizen.** Per routine: prompt uit de Claude Routine overnemen in Hermes-cron, een week parallel, uitvoer vergelijken op Telegram, dan de Claude Routine uit. Volgorde: weekly review, morning brief, client leads, candidate scout, blog weekly, match-and-draft, draft-QA als laatste (persoonsgegevens).
5. **Codex koppelen** aan de repo voor PR-reviews en de `codex`-issues.
6. **WS5 verdelen** volgens de tabel in §3; de `claude`-secties eerst omdat die de goedkeuringslijst en de AVG-schermen zijn die het register belooft.
7. **Eigenaar alleen nog op de telefoon.** Telegram voor opdrachten en meldingen, GitHub voor lezen en mergen, claude.ai/code voor de zeldzame keer dat je zelf in een Claude-sessie wilt kijken. De Windows-app kan uit.

## 8. Wat hier bewust niet in staat

- Hermes, Agent Zero of Codex op de productiedatabase laten werken. Niet doen: één verkeerde UPDATE op `candidates` is een datalek of een wissing, en de scripts vangen dat niet.
- Automatisch mergen bij groene CI. De merge blijft de menselijke stap; dat is de enige plek waar de eigenaar alles ziet.
- Codex of Agent Zero als security-auditor. Een audit van een goedkoper model is geen audit.
- Agent Zero zonder screenshot in een beheerconsole laten klikken. Een WAF-regel of DNS-record dat verkeerd staat, merk je pas als het mis is.
