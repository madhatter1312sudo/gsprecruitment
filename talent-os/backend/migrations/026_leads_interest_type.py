"""
Talent OS — WS-C.10: normalise contact_submissions.interest_type + is_read
on both lead tables (contact_submissions, quiz_submissions).

contact_submissions.interest_type (migrations/002_portal_tables.py) has
always been a free-text VARCHAR(100) -- routers/public.py's submit_lead()
writes whatever LeadSubmit.interest_type the caller sends, unvalidated.
This migration:

  1. Normalises every existing row: NULL or any value outside the
     four-value set below becomes 'overig' -- run *before* the CHECK is
     added, so the ALTER never aborts on legacy/free-text data (there is
     no way to know up front what stray values are already in prod).
  2. Sets a NOT NULL DEFAULT 'overig' and a CHECK on the four-value set
     (werving_selectie | detachering_internationaal | kandidaat | overig)
     -- models/schemas.py's LeadSubmit validator normalises the same way
     before the INSERT (routers/public.py), so in practice nothing ever
     hits the DEFAULT, but it's there so a future direct INSERT (a script,
     a different caller) can't slip a NULL past the column either.
  3. Adds is_read boolean to both contact_submissions (already has it,
     migrations/002 -- ADD COLUMN IF NOT EXISTS is a no-op there) and
     quiz_submissions (does not have it yet). quiz_submissions has no
     interest_type column at all (it's the skill-quiz table, not a lead
     form) so no CHECK is added there -- WS-C.10 spec: "(and
     quiz_submissions if it has one)".

Pattern of 014/015: idempotent. The UPDATE/ALTER COLUMN SET NOT NULL/SET
DEFAULT statements are safe to re-run (a no-op once every row already
satisfies them); the CHECK constraint uses the DROP CONSTRAINT IF EXISTS +
ADD CONSTRAINT pattern from 016/018 (Postgres has no ADD CONSTRAINT IF NOT
EXISTS). No unique indexes, no DO $$ ... END $$ blocks (migrations/_runner.py
splits on a literal ";").
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "026_leads_interest_type"

MIGRATION_SQL = """
UPDATE contact_submissions SET interest_type = 'overig'
WHERE interest_type IS NULL
   OR interest_type NOT IN ('werving_selectie','detachering_internationaal','kandidaat','overig');

ALTER TABLE contact_submissions ALTER COLUMN interest_type SET DEFAULT 'overig';
ALTER TABLE contact_submissions ALTER COLUMN interest_type SET NOT NULL;

ALTER TABLE contact_submissions DROP CONSTRAINT IF EXISTS chk_contact_submissions_interest_type;
ALTER TABLE contact_submissions ADD CONSTRAINT chk_contact_submissions_interest_type
    CHECK (interest_type IN ('werving_selectie','detachering_internationaal','kandidaat','overig'));

ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_contact_submissions_is_read ON contact_submissions(is_read);
CREATE INDEX IF NOT EXISTS idx_quiz_submissions_is_read ON quiz_submissions(is_read);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
