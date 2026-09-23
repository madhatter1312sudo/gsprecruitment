"""
Talent OS -- WS3 (e-mail en Google Sign-In): email_log.

Elke poging om een e-mail te verzenden (verificatie, wachtwoordreset,
talentpool-bevestiging en -herinnering, teamuitnodiging, eigenaarsmelding,
en elke handmatig goedgekeurde outreach-mail) schrijft één rij, ongeacht
of de poging slaagt, mislukt of wordt overgeslagen -- inclusief elke losse
retry-poging (services/email_service.py, backoff 0.5s/2s/8s op
verbindingsfouten en 5xx, nooit op 4xx). `to_hash` is core.privacy.
email_hash(adres): het adres zelf staat nergens in deze tabel, ook niet in
`error` (services/email_service.py haalt elke foutmelding eerst door
core.privacy.redact_emails() voor die kolom weggeschreven wordt).

Puur technisch logboek, geen apart adresveld: bewaartermijn 90 dagen (zie
docs/VERWERKINGSREGISTER.md), infrastructuur-opruiming zoals de overige
applicatielogs -- geen aparte purge-job in deze migratie of dit spoor.

Pattern van 030/032/033/034/036/039: idempotent (CREATE TABLE IF NOT
EXISTS, CREATE INDEX IF NOT EXISTS), geen DO $$ ... END $$ blokken
(migrations/_runner.py splitst op een letterlijke ";"), geen DELETE/DROP.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "040_email_log"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS email_log (
    id          SERIAL PRIMARY KEY,
    template    TEXT NOT NULL,
    to_hash     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'skipped')),
    provider    TEXT,
    provider_id TEXT,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_log_created_at ON email_log(created_at);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
