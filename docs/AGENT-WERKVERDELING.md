# Werkverdeling tussen agents

Doel: het bedrijf draaien vanaf een telefoon, met Hermes als orkestrator op de eigen machine (Omarchy), zonder de Claude-desktop-app op Windows, en met Claude Code alleen voor het werk dat het echt nodig heeft. Dit document legt vast wie wat doet, hoe ze met elkaar praten, en wat er nooit naar een goedkoper model mag.

Aannames over Hermes die dit document doet: het kan cron-taken draaien, shellcommando's en HTTP-aanroepen doen, met Telegram praten, en heeft meerdere profielen met elk een eigen model en eigen instructies. "Agent 0" is hier een Hermes-werkprofiel, geen los product. Klopt een aanname niet, dan verandert de rolverdeling niet, alleen het mechanisme.

## 1. Eén bus: GitHub plus Telegram

Alle agents praten via twee kanalen die er al zijn en die vanaf een telefoon werken.

- **GitHub issues zijn de werkvoorraad.** Elke taak is een issue met één routeringslabel: `hermes`, `agent0`, `codex` of `claude`. Wie het label draagt, doet het werk en rapporteert in het issue. Een PR sluit het issue ("Closes #n"). Zonder label gebeurt er niets; dat is de rem.
- **Telegram is het rapportagekanaal.** Korte meldingen, nooit persoonsgegevens (dat is nu al de regel voor de routines). Vanaf de telefoon geef je opdrachten aan Hermes in Telegram; Hermes maakt er issues van met het juiste label.
- **De repo is de enige bron van waarheid.** `CLAUDE.md` (huisregels), `SITE-DESIGN-SPEC.md`, `docs/VERWERKINGSREGISTER.md`, `docs/SOURCING-SOP.md`. Elk profiel krijgt dezelfde huisregels in zijn systeeminstructie; een goedkoper model mag ze niet minder streng lezen.

Wat hierdoor niet meer nodig is: de Claude-desktop-app als doorgeefluik, Cowork als taakuitvoerder, en een Claude-sessie die elke vier uur wakker wordt om te kijken of er werk is.

## 2. Rollen

### Hermes, hoofdprofiel: orkestrator

Het enige profiel dat opdrachten van de eigenaar aanneemt. Verdeelt, plant, bewaakt, rapporteert. Schrijft zelf geen code.

- Intake vanaf Telegram: opdracht naar issue met label, prioriteit en een korte definitie van klaar.
- Routing volgens tabel §3. Twijfel is `claude`, nooit `agent0`.
- Cron: de zeven routines uit `CLAUDE.md` (morning brief, draft-QA, match-and-draft, client leads, candidate scout, blog weekly, weekly review). Die draaien nu als Claude Routines; ze verhuizen naar Hermes-cron met een goedkoper model, één voor één, na een week parallel draaien.
- Bewaking: CI-status per PR, deploystatus na een merge, `GET /health` van de API, de logregels van de droogloopjobs (`accounts_due` uit de slapend-accountjob). Meldt afwijkingen op Telegram.
- Eigenaarslijsten bijhouden: de checklists in `docs/EMAIL-SETUP.md` §9, de "na de merge"-secties van PR's. Hermes herinnert, de eigenaar doet.

### Hermes, profiel "agent 0": werker voor laag risico

Mechanisch werk op een branch, met PR. Nooit merge, nooit deploy, nooit iets onder §4.

- Kopij en documentatie: meta-omschrijvingen, blogteksten volgens de SOP, registerteksten die de code al doet, vertalingen van Engelse chrome in het adminpaneel.
- Data-operaties via de API met de `X-API-Key`: vacatures seeden (`scripts/seed_pool_vacancies.py`, dry-run eerst), sitemap opnieuw indienen, `system_settings` lezen.
- Tests schrijven voor bestaande gedragingen, afhankelijkheden bijwerken (Dependabot-PR's beoordelen), CI-scripts die rood staan op iets triviaals.
- Kleine, afgebakende frontend- en backendwijzigingen zonder persoonsgegevens: een kolom in een adminlijst, een label, een filter, een lege staat, een sorteerknop op een route die `sort` al kent.
- Als reviewer van eerste lijn op werk van Codex, en omgekeerd.

Agent 0 werkt met de repo-scripts als vangrail: `check_api_contract.py`, `generate_openapi_snapshot.py --check`, `xss_static_check.py`, `css_tokens_check.py`, `admin_ui_check.py`, de testsuite tegen een verse Postgres. Groen is de toegangseis voor een PR; de scripts vervangen daarmee een deel van de menselijke en Claude-review.

### Hermes, profiel "claude code": de aanroep van Claude

Geen eigen rol, maar de manier waarop Hermes Claude Code start zonder desktop-app. Twee mechanismen, kies er één als standaard:

1. **Headless op Omarchy.** `claude -p "<opdracht>" --allowedTools ...` als subprocess, in een checkout van de repo, met het abonnement. Goedkoop in opzet, draait op de eigen machine, verbruikt abonnementsquota. Geschikt voor alles wat binnen één sessie past.
2. **Claude Code GitHub Action.** `anthropics/claude-code-action` in `.github/workflows/`, getriggerd op het label `claude` of een `@claude`-comment. Draait in GitHub, betaald per token via een API-sleutel, onafhankelijk van welke machine aanstaat. Geschikt als de eigen machine uit kan staan en als audittrail (alles staat in het issue).

Aanbeveling: mechanisme 2 als standaard voor `claude`-issues, mechanisme 1 voor interactief werk vanaf de telefoon via Hermes. Het bestaande `gsp-taskdesk`-routine (elke vier uur wakker, meestal niets te doen) vervalt zodra een van beide staat.

### Codex

Tweede coder en tweede reviewer, om Claude te sparen op middelgroot werk zonder persoonsgegevens: frontend-secties van het adminpaneel die alleen bestaande routes tonen (plaatsingen, users, health, pipeline-tabs), portaalschermen, blogindex. Codex kan ook via GitHub reageren op PR's (`@codex`), wat een goedkope eerste review geeft vóór Claude erbij komt.

### Claude Code: alleen het kritieke

Claude doet wat een fout duur maakt of wat een reviewketen met bewijs vereist:

- Alles onder §4 (auth, persoonsgegevens, toestemming, bewaartermijnen, outreach, betalingen, migraties die data raken).
- Architectuur en specs: nieuwe secties in `SITE-DESIGN-SPEC.md`, het verwerkingsregister, wijzigingen aan `deploy.yml` of `docker-compose.yml`.
- De poortwachtersrollen uit `.claude/agents/`: `security-auditor` vóór elke release die auth of persoonsgegevens raakt, `chief-of-staff` als laatste interne verdict op release-PR's, `design-reviewer` op visuele wijzigingen aan de publieke site.
- Incidenten: een 500 op productie, een mislukte migratie, een AVG-verzoek dat vastloopt.
- Werk dat Agent 0 of Codex twee keer heeft laten liggen.

Wat Claude niet meer doet: pollen op issues, routines draaien, kopij, seeds, CI-groen-maken, en reviews van werk dat de scripts al afdekken.

## 3. Routeringstabel

| Soort werk | Label | Reviewer | Chief-of-staff |
|---|---|---|---|
| Kopij, docs, vertalingen, meta | `agent0` | scripts + Codex | nee |
| Seeds, sitemap, data-ops via API | `agent0` | scripts | nee |
| Dependabot, CI-fix, tests voor bestaand gedrag | `agent0` | scripts + Codex | nee |
| Adminscherm of portaalscherm zonder persoonsgegevens (plaatsingen, users, health, pipeline-weergave, analytics) | `codex` of `agent0` | Codex/Agent 0 kruiselings, Claude `code-reviewer` bij de PR | nee |
| Publieke site, visueel | `codex` of `agent0` | Claude `design-reviewer` bij de PR | alleen bij een hele pagina |
| Adminscherm met persoonsgegevens, toestemming, bewaartermijnen, AVG-wissen, referral-intake, suppressielijst | `claude` | `security-auditor` + `code-reviewer` | ja |
| Backend: auth, e-mailverzending, matching, outreach, migraties | `claude` | `security-auditor` + `code-reviewer` | ja |
| Spec, register, SOP, infra | `claude` | `code-reviewer` | ja |
| Routines (dagelijks/wekelijks) | Hermes-cron | geen | nee |
| Bewaking en rapportage | Hermes | geen | nee |

Voor WS5 betekent dit concreet: de goedkeuringslijst bewaartermijnen, toestemmingen en referral-intake, AVG-wissen en suppressielijst gaan naar `claude`; plaatsingen, pipeline-tab, users/unlock/health/prospects, de job-alertschakelaar in het kandidatenportaal en het klantportaal (kanban, analytics, contacten, teamtabel) gaan naar `codex`/`agent0` met een Claude-codereview bij de PR.

## 4. Wat nooit naar een goedkoper model gaat

Deze regels staan in `CLAUDE.md` en gelden voor elk profiel; hier staat welke dus alleen door Claude met de volledige keten worden aangeraakt.

- Alles wat schrijft naar `candidates`, `users`, `talentpool_optin_requests`, `suppression_list`, `retention_review_*`, `job_alert_sends`, of leest uit een art. 15-export.
- Alles wat een e-mail verstuurt. Outreach blijft draft-only: geen enkel profiel mag een verzendpad toevoegen.
- Auth, MFA, tokens, API-sleutels, de WAF-regel, DNS.
- Migraties die bestaande rijen wijzigen (normalisaties, constraints).
- Merge naar main en deploy: dat blijft de eigenaar, met één uitzondering die de eigenaar per sessie expliciet geeft.

Hermes en Agent 0 krijgen daarom geen admin-JWT en geen databasetoegang tot productie; alleen de `X-API-Key` voor de publieke en kandidaat/vacature-routes, en GitHub-schrijfrechten op branches en issues, niet op main.

## 5. Kan Hermes met de Claude-desktop-app, Cowork of de cloudomgevingen praten?

Kort: niet met de desktop-app of Cowork, wel met Claude Code in de cloud, en dat laatste is genoeg.

- **Claude-desktop-app en Cowork** hebben geen API waar iets van buiten in kan schrijven. De desktop-app kan wel MCP-servers gebruiken, maar dat is de app die naar buiten praat, niet andersom. Cowork is een lokale desktopfunctie; niets kan een Cowork-taak op afstand starten. Conclusie: die twee vervallen in dit model. Alles wat Cowork deed (taken uit de desktop-app aan Claude geven) doet Hermes via GitHub-issues met het label `claude`.
- **Claude Code in de cloud** (claude.ai/code) is te bereiken op drie manieren zonder desktop-app: (1) vanaf de telefoon in de browser of de mobiele app, (2) via Routines die op schema of op aanroep een sessie starten, (3) via de GitHub Action, die effectief een Claude Code-run in CI is. Hermes gebruikt 3 als standaard. Binnen een lopende cloudsessie kan Claude zelf nieuwe sessies en Routines aanmaken (dat gebeurt nu ook), dus als Hermes één sessie start, kan die de rest orkestreren.
- **Headless op Omarchy** is de vierde weg: Hermes roept `claude -p` aan als subprocess. Dat is de "profiel 3"-constructie. Werkt zonder cloud, maar alleen als de machine aanstaat.

Wat Hermes dus praktisch doet bij een `claude`-issue: label zetten (Action start), of `claude -p` starten met het issuenummer als opdracht. Terugkoppeling komt als comment in het issue en als PR; Hermes leest die en meldt op Telegram.

## 6. Tokenregels voor Claude

- Eén reviewketen per PR, geschaald naar risico zoals `CLAUDE.md` voorschrijft. Geen tweede ronde omdat een reviewer een testgat vond dat een script had kunnen vangen: voeg dan het script toe en laat Agent 0 het draaien.
- Niet meer dan twee parallelle Claude-agents per sessie tenzij het echt onafhankelijke sporen zijn.
- Geen Claude-sessie die polt. `gsp-taskdesk` uit zodra Hermes de issues bewaakt.
- Routines op Hermes, niet op Claude, behalve `gsp-draft-qa` zolang die persoonsgegevens beoordeelt (dan `claude`, wekelijks in plaats van dagelijks, of Hermes met een lokaal model en zonder de gegevens te bewaren).
- Chief-of-staff alleen op release-PR's (auth, persoonsgegevens, hele pagina's, infra). Niet op kopij, docs, seeds, kleine schermen.
- Screenshots en metingen door scripts, niet door een agent die ze beschrijft: `admin_ui_check.py`, `admin_sections_check.py`, de sweep-scripts uit de kaartenronde horen in `scripts/` en draaien in CI.

## 7. Migratiestappen, in volgorde

1. **Labels en werkvoorraad.** Vier labels in GitHub aanmaken. Hermes-orkestrator krijgt: issues lezen en aanmaken, comments, branches en PR's; niet mergen. Eerste week: alleen intake en routing, nog niets uitvoeren.
2. **Agent 0 aan het werk op de openstaande eigenaarslijst.** Seed van de 27 vacatures op productie (dry-run, `--apply`, `GET /api/public/jobs` moet 27 geven), sitemap opnieuw indienen, Engelse chrome in het adminpaneel vertalen, de vijf ontbrekende tokens in `theme.css`. Dit is de proef of Agent 0 met de scripts als vangrail veilig genoeg is.
3. **Claude-aanroep zonder desktop.** GitHub Action op het label `claude` inrichten (API-sleutel als repo-secret, nooit in code), één proefissue. Daarna `gsp-taskdesk` uitzetten.
4. **Routines verhuizen.** Per routine: prompt uit de Claude Routine overnemen in Hermes-cron, een week parallel, uitvoer vergelijken op Telegram, dan de Claude Routine uit. Volgorde: weekly review, morning brief, client leads, candidate scout, blog weekly, match-and-draft, draft-QA als laatste (persoonsgegevens).
5. **Codex koppelen** aan de repo voor PR-reviews en de `codex`-issues.
6. **WS5 verdelen** volgens de tabel in §3; de `claude`-secties eerst omdat die de goedkeuringslijst en de AVG-schermen zijn die het register belooft.
7. **Eigenaar alleen nog op de telefoon.** Telegram voor opdrachten en meldingen, GitHub voor lezen en mergen, claude.ai/code voor de zeldzame keer dat je zelf in een Claude-sessie wilt kijken. De Windows-app kan uit.

## 8. Wat hier bewust niet in staat

- Hermes of Agent 0 met een lokaal model op de productiedatabase laten werken. Niet doen: één verkeerde UPDATE op `candidates` is een datalek of een wissing, en de scripts vangen dat niet.
- Automatisch mergen bij groene CI. De merge blijft de menselijke stap; dat is de enige plek waar de eigenaar alles ziet.
- Codex of Agent 0 als security-auditor. Een audit van een goedkoper model is geen audit.
