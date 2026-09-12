"""
Talent OS -- WS3b/WS3c, tweede reparatieronde: het afmeldtoken aan zijn
kanaal binden, en de slapend-accountwaarschuwing laten doorlopen langs
een geblokkeerd of onbezorgbaar adres.

`job_alert_sends.oneclick_token_hash` (B1, tokenbinding):
één verzending droeg tot nu toe één token, dat op twee plaatsen in
dezelfde mail stond -- in het fragment van de voettekstlink
(`/unsubscribe#token=...`) en in de querystring van de
`List-Unsubscribe`-URL die RFC 8058 voorschrijft. De querystring-variant
staat per definitie in elke access-, proxy- en edge-logregel die het
verzoek passeerde. Wie zo'n URL uit een log haalde, kon hetzelfde token
in de BODY van `POST /api/public/unsubscribe` plakken en daarmee
`scope=all` bereiken: toestemming ingetrokken en het adres op de
blokkeerlijst, onomkeerbaar. Ronde 1 keek daarvoor naar de plek van het
token in het verzoek (querystring -> altijd `alerts`), maar dat is een
eigenschap van het verzoek, niet van het token.

Twee hashes maken er een eigenschap van het token van. Elke verzending
krijgt twee losse tokens van 32 random bytes: `token_hash` hoort bij de
voettekstlink en is de enige weg naar `scope=all`; `oneclick_token_hash`
hoort bij de `List-Unsubscribe`-URL en levert altijd `alerts`, wat de
body, de querystring of de opgegeven scope ook zegt. Een gelekt
one-click-token kan daarmee niet méér dan waarvoor het is uitgegeven.

`job_alert_sends.oneclick_used_at` (C3, derde ronde): twee tokens deelden
één `used_at`. Wie een one-click-URL uit een access log haalde en één keer
POSTte, meldde de ontvanger niet alleen af voor alerts maar doodde daarmee
ook diens FRAGMENTtoken uit dezelfde verzending -- de enige weg naar
`scope=all`. De ontvanger merkte daar niets van: het antwoord van
`POST /api/public/unsubscribe` is voor elk token identiek, ook voor een
verbruikt token. Daarmee kon een gelekt one-click-token wél iets wat het
niet mag: iemand de weg naar een volledige intrekking afsnijden. Elk token
kijkt en stempelt vanaf nu uitsluitend zijn eigen kolom, zodat de twee
links elk één keer en onafhankelijk van elkaar werken. Nullable en zonder
default: NULL betekent onverbruikt, exact zoals `used_at`.

`users.dormant_warning_attempt_at` (C2, backoff): `dormant_warning_attempts`
telde drie mislukte verzendingen op drie opeenvolgende dagen, en sinds C2
stempelt de derde mislukking `dormant_warning_skipped_at` -- waarmee een
storing van twee etmalen bij de e-maildienstverlener een werkend adres
onbezorgbaar zou verklaren en het account 30 dagen later op de
beoordelingslijst zou zetten. Deze kolom houdt het tijdstip van de laatste
poging vast; `DORMANT_WARNING_SQL` eist er `core/retention.py
DORMANT_WARNING_RETRY_DAYS` tussen. Een vast interval, geen oplopende
reeks. `LOGIN_STAMP_SQL` zet hem samen met de teller terug op NULL.

Nullable, want de rijen van vóór deze migratie hebben geen tweede token;
die houden hun bestaande `token_hash`-weg. UNIQUE om dezelfde reden als
`token_hash` dat is: twee verzendingen kunnen nooit hetzelfde token
dragen, en de afmeld-lookup blijft een puntquery op een index. Als los
`CREATE UNIQUE INDEX IF NOT EXISTS` en niet als kolomconstraint, omdat
alleen de index-vorm idempotent is; NULL-waarden zijn in Postgres
onderling distinct, dus bestaande rijen botsen niet.

`users.dormant_warning_skipped_at` (B3, blokkeerlijst):
`services/scheduler.py`'s `dormant_account_warning_job` filterde
geblokkeerde adressen uit ná de `LIMIT` van de selector. Zo'n rij werd
daardoor nooit gestempeld, bleef onder `ORDER BY last_login_at ASC`
vooraan staan en verbruikte elke dag opnieuw een plek onder het
dagplafond; bij een paar honderd geblokkeerde accounts waarschuwde de
job niemand meer. Bovendien is een STOP een verbod op berichten, geen
toestemming tot onbeperkt bewaren -- zonder stempel bereikte zo'n
account ook de maandelijkse beoordelingslijst nooit.

Deze kolom is de mailloze tegenhanger van `dormant_warning_sent_at`: de
job stempelt hem, schrijft een `audit_log`-rij `dormant_warning_suppressed`
(met alleen de sha256 van het adres) en verstuurt niets.
`core/retention.py`'s `PORTAL_ACCOUNT_INACTIVE_SQL` accepteert hem naast
`dormant_warning_sent_at`, met dezelfde 30 dagen ertussen, en
`DORMANT_WARNING_SQL` sluit de rij erop uit -- zelfde vorm als de
bestaande `< last_login_at`-vergelijking, zodat een nieuwe login een
nieuwe cyclus begint.

`users.dormant_warning_attempts` (B4, structureel falende verzending):
een dood adres leverde elke dag een mislukte verzending op, werd nooit
gestempeld en hield zo permanent een plek onder hetzelfde dagplafond
bezet. De job hoogt deze teller op bij een mislukte verzending;
`DORMANT_WARNING_SQL` sluit rijen met drie of meer pogingen uit, en elk
inlogpad zet hem terug op 0 (`core/retention.py LOGIN_STAMP_SQL`, gebruikt
door `routers/auth.py` en `routers/mfa.py`). NOT NULL DEFAULT 0 zodat
bestaande rijen meteen een bruikbare waarde hebben en de selector geen
NULL-tak nodig heeft.

`system_settings.job_alerts_enabled` (reparatieronde, de tweede rem):
`docs/VERWERKINGSREGISTER.md` rij 20 en `core/config.py` beschrijven twee
schakelaars die allebei standaard op droogloop staan -- de env-master
`JOB_ALERTS_ENABLED` en deze admin-bewerkbare DB-vlag. Die tweede bestond
niet: `services/scheduler.py`'s `_flag_enabled()` geeft True terug bij een
ONTBREKENDE sleutel (dat is de bedoeling -- geen enkele andere vlag hoeft
eerst te worden aangemaakt om "aan" te zijn), en geen migratie maakte deze
rij aan. Er was dus precies één rem, en de twee documenten beloofden er
twee. Deze INSERT maakt de belofte waar op de manier die de eigenaar
daarna kan bedienen: de rij staat er, op `false`, en het adminpaneel kan
hem omzetten. `ON CONFLICT DO NOTHING` zodat een bestaande waarde -- ook
een die de eigenaar zelf al op `true` heeft gezet -- nooit wordt
teruggezet door een herhaalde deploy.

Patroon van 030/032/033/034/036/037/039/040/041: idempotent (ADD COLUMN
IF NOT EXISTS, CREATE INDEX IF NOT EXISTS), geen `DO $$ ... END $$`-blokken
(migrations/_runner.py splitst op een letterlijke ";"), geen DELETE/DROP.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "042_alerts_token_binding_dormant_skip"

MIGRATION_SQL = """
ALTER TABLE job_alert_sends ADD COLUMN IF NOT EXISTS oneclick_token_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_job_alert_sends_oneclick_token_hash
    ON job_alert_sends(oneclick_token_hash);

ALTER TABLE job_alert_sends ADD COLUMN IF NOT EXISTS oneclick_used_at TIMESTAMPTZ;

ALTER TABLE users ADD COLUMN IF NOT EXISTS dormant_warning_skipped_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS dormant_warning_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS dormant_warning_attempt_at TIMESTAMPTZ;

INSERT INTO system_settings (key, value, description) VALUES
    ('job_alerts_enabled', 'false', 'Tweede rem op de dagelijkse vacature-alerts, naast JOB_ALERTS_ENABLED in env')
ON CONFLICT (key) DO NOTHING;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
