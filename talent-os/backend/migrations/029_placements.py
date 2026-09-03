"""
Talent OS — WS-C.7: placements (minimaal) + immigratiestatus. PROVISIONAL.

Everything this migration adds is provisional: the pricing/margin factors
it makes room for (eor_cost_factor, fee_percentage, etc.) are owner
decisions not yet settled, and nothing here is published to the public
site or the client portal (routers/placements.py, added in the same PR,
is admin-only — Bearer admin JWT — with no client-portal router at all).
core/margin.py's compute_margin() flags every result it returns with
provisional: true for the same reason.

Two things land here:

1. `placements` — one row per candidate-job-client placement, minimal by
   design (WS-C.7 scope explicitly excludes invoicing/contract-document
   tracking, which is a separate later workstream). Columns:
     - candidate_id / job_id / client_id  FK -> candidates/job_orders/
       clients(id). No ON DELETE action specified (default RESTRICT) --
       a placement is a fiscal record (7-year retention floor, see
       core/retention.py's placed_candidate row) and must never silently
       vanish because someone deletes the client/job/candidate row it
       points to; soft-delete (deleted_at) is how those go away instead.
     - placement_type   werving_selectie (W&S, one-off placement fee) |
       detachering (secondment, ongoing bill/purchase spread).
     - start_date / end_date            date bounds of the assignment.
     - hourly_bill_rate                 what the client is billed, per
       hour (detachering, billing_basis='per_uur').
     - monthly_purchase_price           what GSP pays its EOR/subcontract
       partner per month for this placement (detachering cost side).
     - eor_partner                      free-text only -- never a specific
       partner name hardcoded anywhere in this codebase or its tests,
       same house rule as everywhere else PII/vendor-identity could leak.
     - eor_cost_factor                  numeric(6,4) multiplier applied to
       a gross monthly salary (an input to core/margin.py, not a column
       on this table) to derive monthly_purchase_price when the latter
       isn't given directly -- e.g. 1.575 in the WS-C.7 test vectors.
     - billing_basis    vast_maandbedrag (fixed monthly amount) | per_uur
       (per hour, using hourly_bill_rate × expected_billable_hours).
     - expected_billable_hours          numeric(6,2) -- monthly hours used
       by core/margin.py's per_uur revenue calculation.
     - fee_type          percentage | vast -- how the W&S fee is set.
     - fee_percentage / fee_amount      one or the other populated
       depending on fee_type; core/margin.py resolves fee_amount when
       fee_type='vast', else fee_percentage × an annual-salary input.
     - one_off_costs     jsonb, default '[]' -- ad-hoc one-off cost line
       items (e.g. relocation, work-permit filing fee); always
       json.dumps()'d before writing (never a raw dict/list -- see
       commit 72b4bcd) and coerced back to [] on read if NULL.
     - status   concept -> actief -> beeindigd, or geannuleerd from
       concept/actief -- routers/placements.py validates the transition
       graph before writing (no direct concept -> beeindigd, no leaving
       a terminal state).
     - notes / created_by / created_at / updated_at / deleted_at -- same
       soft-delete + audit-friendly shape as client_contacts
       (migrations/024).

2. On `candidates` — immigratiestatus columns for non-EU/EEA hires:
     - nationality             text, free text.
     - needs_work_permit       boolean, nullable (unknown until asked).
     - kennismigrant_status    nvt | aangevraagd | toegekend | afgewezen --
       the "highly skilled migrant" (kennismigrant) visa-route status.
     - ruling_30pct_status     nvt | aangevraagd | toegekend | afgewezen --
       the 30%-ruling tax facility status, same four-value set (a
       different scheme from kennismigrant_status but the same
       application lifecycle shape, so it reuses the same CHECK values).
     - ind_case_number         text, free text -- the IND (Immigratie- en
       Naturalisatiedienst) case/reference number once filed.
   These five columns fall under the same 7-year "geplaatste kandidaat"
   retention floor as the rest of a placed candidate's contract/fiscal
   data (core/retention.py's placed_candidate row, bron_opmerking
   "fiscale bewaarplicht") -- they exist only to support an active or
   past placement, so they are erased by routers/gdpr.py's
   erase_person() alongside every other candidates.* PII column, not
   retained past that erasure just because the visa data itself might
   otherwise persist longer than 7 years. erase_person()'s candidates
   UPDATE is extended in this same PR to null all five.

Pattern of 014/015/024: idempotent (CREATE TABLE IF NOT EXISTS / ALTER
TABLE ADD COLUMN IF NOT EXISTS), CHECK constraints declared inline (no
DROP/ADD CONSTRAINT dance -- IF NOT EXISTS on the outer statement is
enough, matching 024's reasoning), no unique index of any kind (WS-C.7
spec: no unique index on placements), no `DO $$ ... END $$` block
(migrations/_runner.py splits on a literal ";").
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "029_placements"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS placements (
    id                       SERIAL PRIMARY KEY,
    candidate_id             INTEGER NOT NULL REFERENCES candidates(id),
    job_id                   INTEGER NOT NULL REFERENCES job_orders(id),
    client_id                INTEGER NOT NULL REFERENCES clients(id),
    placement_type           TEXT NOT NULL CHECK (placement_type IN ('werving_selectie','detachering')),
    start_date               DATE,
    end_date                 DATE,
    hourly_bill_rate         NUMERIC(10,2),
    monthly_purchase_price   NUMERIC(10,2),
    eor_partner              TEXT,
    eor_cost_factor          NUMERIC(6,4),
    billing_basis            TEXT CHECK (billing_basis IS NULL OR billing_basis IN ('vast_maandbedrag','per_uur')),
    expected_billable_hours  NUMERIC(6,2),
    fee_type                 TEXT CHECK (fee_type IS NULL OR fee_type IN ('percentage','vast')),
    fee_percentage           NUMERIC(5,2),
    fee_amount               NUMERIC(10,2),
    one_off_costs            JSONB NOT NULL DEFAULT '[]',
    status                   TEXT NOT NULL DEFAULT 'concept' CHECK (status IN ('concept','actief','beeindigd','geannuleerd')),
    notes                    TEXT,
    created_by               INTEGER REFERENCES users(id),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ,
    deleted_at               TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_placements_candidate ON placements(candidate_id);
CREATE INDEX IF NOT EXISTS idx_placements_job ON placements(job_id);
CREATE INDEX IF NOT EXISTS idx_placements_client ON placements(client_id);
CREATE INDEX IF NOT EXISTS idx_placements_status ON placements(status);
CREATE INDEX IF NOT EXISTS idx_placements_deleted_at ON placements(deleted_at);

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS nationality text;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS needs_work_permit boolean;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS kennismigrant_status text CHECK (kennismigrant_status IS NULL OR kennismigrant_status IN ('nvt','aangevraagd','toegekend','afgewezen'));
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS ruling_30pct_status text CHECK (ruling_30pct_status IS NULL OR ruling_30pct_status IN ('nvt','aangevraagd','toegekend','afgewezen'));
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS ind_case_number text;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
