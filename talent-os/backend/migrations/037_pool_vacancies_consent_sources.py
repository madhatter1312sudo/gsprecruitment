"""
Talent OS -- vacatures met anonieme opdrachtgever: clients.is_internal +
talentpool_optin_requests job-koppeling + bredere consent_source-sets.

Achtergrond: de eigenaar heeft besloten dat de site een bredere set
vacatures toont over de vier disciplines (embedded software, mechatronica,
OT-cybersecurity, testrollen) zonder de opdrachtgever te noemen
(docs/VERWERKINGSREGISTER.md paragraaf 6, punt 11). Dat vraagt om een
manier om "eigen"/anonieme vacatures te onderscheiden van vacatures voor
een echte, met naam bekende opdrachtgever, en om de sollicitatieroute
(talentpool, dubbele opt-in) aan een specifieke vacature te kunnen
koppelen.

Kolommen:
  - clients.is_internal BOOLEAN NOT NULL DEFAULT false -- vervangt de
    naam-gebaseerde herkenning van migrations/016_job_orders_columns.py's
    docstring ("client_id, niet titel-tekst") met een expliciete vlag.
    routers/jobs.py projecteert deze als `anonymous_client` op elke
    publieke vacature; routers/admin.py's analytics en
    services/scheduler.py's draft_outreach gebruiken hem om interne
    opdrachtgevers respectievelijk uit te sluiten of te anonimiseren.
    Backfill: de bestaande 'GSP Talent Pool'-klant (migrations/012, de zes
    demo-vacatures) wordt is_internal=true; een tweede interne klantrij
    'GSP Recruitment (anonieme opdrachtgever)' wordt aangemaakt voor de
    nieuwe, niet-demo pool-vacatures (is_demo blijft false voor die rij --
    het zijn geen placeholder-vacatures, wel vacatures zonder genoemde
    opdrachtgever).
  - talentpool_optin_requests.job_id INTEGER REFERENCES job_orders(id)
    ON DELETE SET NULL -- optionele koppeling wanneer het opt-in-formulier
    vanaf een vacaturepagina komt (contract: POST /api/public/talentpool-
    optin, bron 'vacancy_apply'); ON DELETE SET NULL omdat de rij zelf
    (het aanmeldbewijs) blijft bestaan als de vacature later wordt
    verwijderd -- zelfde redenering als migrations/029_placements.py voor
    zijn eigen nullable FK's.
  - talentpool_optin_requests.job_alerts BOOLEAN NOT NULL DEFAULT false --
    of de aanvrager ook algemene vacature-alerts wil; vandaag alleen
    bewaard op deze tabel (candidates heeft nog geen job_alerts-kolom).

consent_source-sets verbreed (twee losstaande CHECK constraints, beide nu
uitgebreid met 'vacancy_apply' en 'referral'):
  - candidates.consent_source (migrations/030_talentpool_consent.py,
    regel 69): auto-benoemde constraint uit die migratie was
    `candidates_consent_source_check` (opgezocht op een verse database --
    Postgres benoemt een inline CHECK op ADD COLUMN impliciet). Vervangen
    door een expliciet benoemde `chk_candidates_consent_source`, patroon
    migrations/016/018/026 (DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT,
    want Postgres kent geen `ADD CONSTRAINT IF NOT EXISTS` voor een CHECK).
  - talentpool_optin_requests.source (migrations/030, regel 77): idem,
    auto-benoemde constraint was `talentpool_optin_requests_source_check`,
    vervangen door `chk_talentpool_optin_requests_source`.
  Beide statement-paren droppen zowel de oorspronkelijke auto-benoemde
  constraint als hun eigen nieuwe naam vóór het opnieuw toevoegen, zodat
  het script twee keer kan draaien zonder "constraint already exists".

Pattern van 016/030: idempotent (ADD COLUMN IF NOT EXISTS, DROP CONSTRAINT
IF EXISTS, INSERT ... WHERE NOT EXISTS), geen `DO $$ ... END $$`-blokken
(migrations/_runner.py splitst op een letterlijke ";").
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "037_pool_vacancies_consent_sources"

MIGRATION_SQL = """
ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_internal BOOLEAN NOT NULL DEFAULT false;

UPDATE clients SET is_internal = true WHERE company_name = 'GSP Talent Pool';

INSERT INTO clients (company_name, domain, is_internal)
SELECT 'GSP Recruitment (anonieme opdrachtgever)', 'gsprecruitment.nl', true
WHERE NOT EXISTS (
    SELECT 1 FROM clients WHERE company_name = 'GSP Recruitment (anonieme opdrachtgever)'
);

ALTER TABLE talentpool_optin_requests ADD COLUMN IF NOT EXISTS job_id INTEGER REFERENCES job_orders(id) ON DELETE SET NULL;
ALTER TABLE talentpool_optin_requests ADD COLUMN IF NOT EXISTS job_alerts BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE candidates DROP CONSTRAINT IF EXISTS candidates_consent_source_check;
ALTER TABLE candidates DROP CONSTRAINT IF EXISTS chk_candidates_consent_source;
ALTER TABLE candidates ADD CONSTRAINT chk_candidates_consent_source
    CHECK (consent_source IN ('portal','kandidaten_page','blog_cta','admin','vacancy_apply','referral'));

ALTER TABLE talentpool_optin_requests DROP CONSTRAINT IF EXISTS talentpool_optin_requests_source_check;
ALTER TABLE talentpool_optin_requests DROP CONSTRAINT IF EXISTS chk_talentpool_optin_requests_source;
ALTER TABLE talentpool_optin_requests ADD CONSTRAINT chk_talentpool_optin_requests_source
    CHECK (source IN ('kandidaten_page','blog_cta','vacancy_apply','referral'));

CREATE INDEX IF NOT EXISTS idx_clients_is_internal ON clients(is_internal);
CREATE INDEX IF NOT EXISTS idx_talentpool_optin_requests_job_id ON talentpool_optin_requests(job_id);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
