"""
Talent OS -- WS3b/WS3c: referral-bevestiging, slapend-accountwaarschuwing
en job-alerts met opt-in en een-klik-afmelden.

Vijf kolommen op `candidates` plus een tabel `job_alert_sends`.

`referral_confirmed_at` / `referred_by` (WS3b, referral-bevestiging):
een referral-kandidaat (`lawful_basis = 'toestemming_referral'`, SOP §1.3)
wordt door een mens aangedragen, niet door de persoon zelf. `referred_by`
legt intern vast wie hem aandroeg (de naam/relatie die het Art. 14-blok in
de referral-variant, SOP §3.2, noemt); `referral_confirmed_at` wordt gezet
zodra de persoon zelf op de bevestigingslink in die eerste mail klikt
(`routers/public.py talentpool_confirm()` bij `source = 'referral'`).

Dat tweede veld is een reactiesignaal, geen sierkolom: `core/retention.py`'s
`referral`-rij deelde tot nu toe letterlijk `SOURCED_NO_RESPONSE_SQL` met
`sourced_no_response` (alleen de `lawful_basis`-parameter verschilde), dus
een referral die wel degelijk had gereageerd door te bevestigen, bleef na 3
maanden gewoon op de maandelijkse beoordelingslijst staan. De nieuwe
`REFERRAL_NO_RESPONSE_SQL` voegt `AND c.referral_confirmed_at IS NULL` toe;
de bewaartermijn zelf (3 maanden na `date_found`) verandert niet, alleen wie
er als "geen reactie" telt.

`job_alert_optin_at` / `job_alert_unsubscribed_at` / `job_alert_last_sent_at`
(WS3c, job-alerts): een kandidaat meldt zich zelf aan voor vacature-alerts,
via de portaalschakelaar (`PUT /api/v1/candidate/job-alerts`) of via het
bestaande `job_alerts`-vinkje op `talentpool_optin_requests`
(migrations/037), dat bij bevestiging wordt overgenomen. Afmelden zet
`job_alert_unsubscribed_at` (een-klik, `POST /api/public/unsubscribe`);
`job_alert_last_sent_at` maakt de dagelijkse digest idempotent per
kandidaat, zelfde vorm als `consent_reminder_sent_at` bij
`talentpool_reminder_job`.

`job_alert_sends`: één rij per verzonden digest, met de vacatures die erin
stonden (`job_ids`) en de sha256 van het een-klik-afmeldtoken
(`core.security.hash_token`, net als `talentpool_optin_requests.token_hash`
en `users.verification_token_hash` -- het ruwe token bestaat alleen in de
uitgaande mail). `used_at` markeert een verbruikt token, zodat hergebruik
niets meer doet. `token_hash` is UNIQUE: twee verzendingen kunnen nooit
hetzelfde token dragen, en de afmeld-lookup is een puntquery op een index.
`ON DELETE CASCADE` op `candidate_id`: verdwijnt de kandidaatrij hard, dan
heeft het afmeldtoken niets meer om naar te wijzen.

Patroon van 030/032/033/034/036/037/039/040: idempotent (ADD COLUMN IF NOT
EXISTS, CREATE TABLE/INDEX IF NOT EXISTS), geen `DO $$ ... END $$`-blokken
(migrations/_runner.py splitst op een letterlijke ";"), geen DELETE/DROP.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "041_email_alerts_referral"

MIGRATION_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS referral_confirmed_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS referred_by TEXT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS job_alert_optin_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS job_alert_unsubscribed_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS job_alert_last_sent_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS job_alert_sends (
    id           SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_ids      INTEGER[] NOT NULL DEFAULT '{}',
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    token_hash   TEXT NOT NULL UNIQUE,
    used_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_job_alert_sends_candidate_id ON job_alert_sends(candidate_id);
CREATE INDEX IF NOT EXISTS idx_job_alert_sends_sent_at ON job_alert_sends(sent_at);

CREATE INDEX IF NOT EXISTS idx_candidates_job_alert_optin_at ON candidates(job_alert_optin_at)
    WHERE job_alert_optin_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_candidates_referral_confirmed_at ON candidates(referral_confirmed_at)
    WHERE referral_confirmed_at IS NOT NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
