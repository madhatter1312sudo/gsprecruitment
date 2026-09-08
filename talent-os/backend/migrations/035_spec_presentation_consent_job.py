"""
Talent OS — spec-presentatietoestemming: schrijfpad (§6 punt 10,
docs/VERWERKINGSREGISTER.md).

`candidates.consent_spec_presentation_at` (migrations/018) bestond al maar
werd nergens geschreven; alleen gelezen door `routers/client.py`
(`_project_candidate_public()` e.a.) en de weigeringslogica van
`routers/outreach.py`. Deze migratie voegt niet de kolom zelf toe (die
bestaat al) maar het enige stukje schema dat het nieuwe admin-schrijfpad
(PATCH /api/v1/admin/candidates/{id}/spec-presentation-consent,
routers/admin.py) nodig heeft en dat nog ontbreekt: een verwijzing naar de
rol/vacature waarvoor die toestemming is gegeven, zodat de belofte in
website/privacy.html ("toestemming voor een specifieke rol") ook
daadwerkelijk een rol vastlegt, niet alleen een tijdstempel.

Keuze (afgewogen tegen een aparte tabel met een rij per opdrachtgever/rol
per kandidaat): één nullable FK-kolom, geen nieuwe tabel. Redenen, en
waarom dit voor nu volstaat in plaats van later moeizaam terug te
schroeven:
  - Er is nog geen enkele plaatsing (zie CLAUDE.md-context van deze taak)
    en een bureau van één persoon presenteert een kandidaat in de praktijk
    nooit aan twee opdrachtgevers tegelijk voor twee verschillende rollen
    binnen dezelfde toestemmingsperiode -- een geschiedenis-tabel zou vandaag
    altijd hoogstens één actieve rij per kandidaat bevatten.
  - `consent_spec_presentation_at` is en blijft één tijdstempel per
    kandidaat (globaal, geen rij per opdrachtgever) -- dat blijft zo, deze
    migratie voegt alleen de rolverwijzing tóe aan diezelfde ene rij, ze
    maakt het bestaande gedrag niet complexer. `routers/client.py` en
    `routers/outreach.py` blijven dus ongewijzigd: die lezen alleen of de
    toestemming er is (`consent_spec_presentation_at IS NOT NULL`), niet
    voor welke rol.
  - Restrisico, expliciet vastgelegd in VERWERKINGSREGISTER.md §6 punt 10:
    zodra er meerdere opdrachtgevers tegelijk in de pijplijn zitten, dekt
    één kolom per kandidaat dat niet meer en is een aparte tabel (candidate
    x job x client, met een eigen geldig-vanaf/ingetrokken-op) alsnog
    nodig. Tot die tijd is dat over-engineering voor de huidige praktijk.

Kolom:
  - consent_spec_presentation_job_id INTEGER REFERENCES job_orders(id) --
    de rol waarvoor de huidige (of laatst ingetrokken) spec-presentatie-
    toestemming gold. NULL zolang er geen toestemming is vastgelegd, en
    weer NULL na intrekking (zelfde levenscyclus als
    consent_spec_presentation_at zelf -- zie routers/admin.py
    admin_update_spec_presentation_consent()). Geen ON DELETE-clausule
    nodig: job_orders-rijen worden nooit hard verwijderd (soft-delete via
    deleted_at, zie migrations/000_baseline.py), dus deze FK wordt nooit
    door een verwijderde rij ontkoppeld.

Patroon van 014/015/018/024/030/031: idempotent (ADD COLUMN IF NOT
EXISTS), geen `DO $$ ... END $$;`-blokken (migrations/_runner.py splitst
op een letterlijke ";").
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "035_spec_presentation_consent_job"

MIGRATION_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_spec_presentation_job_id INTEGER REFERENCES job_orders(id);
CREATE INDEX IF NOT EXISTS idx_candidates_consent_spec_presentation_job_id ON candidates(consent_spec_presentation_job_id) WHERE consent_spec_presentation_job_id IS NOT NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
