#!/usr/bin/env python3
"""
Talent OS -- seed script for the "vacatures met anonieme opdrachtgever" pool
(WS-4, migrations/037_pool_vacancies_consent_sources.py).

Reads talent-os/backend/data/pool_vacancies.json -- a list of objects
shaped like AdminJobCreate (models/schemas.py) plus a `slug` field, without
client_id or status: this script supplies both. Every row is inserted
under the internal client 'GSP Recruitment (anonieme opdrachtgever)'
(migrations/037's second is_internal=true client row) with status='open',
so it appears immediately on the public job board (routers/jobs.py
PUBLIC_JOB_WHERE) as an anonymous-opdrachtgever vacancy. is_demo stays
false -- these are not placeholder vacancies (migrations/016's six seed
jobs under the *other* internal client), they are real, open vacatures
the owner chose to publish without naming the opdrachtgever.

Idempotent on (client_id, title, seniority): a row whose (title,
seniority) pair already exists under the internal client is reported
"bestaat" and left untouched, even if description/salary/etc. changed in
the JSON -- this script only ever inserts, it never updates an existing
job order (an admin edits an existing vacancy through the admin panel,
not by re-running this script).

Draaiboek
---------
1. Dry-run eerst (standaard, geen vlag nodig):
       python3 scripts/seed_pool_vacancies.py
   Print per vacature "nieuw" (zou worden ingevoerd) of "bestaat" (al
   aanwezig, wordt overgeslagen). Niets wordt geschreven.

2. Als de dry-run diff klopt, voer echt in:
       python3 scripts/seed_pool_vacancies.py --apply
   Print dezelfde diff, dit keer met het nieuw aangemaakte job_orders.id
   per "nieuw"-rij.

3. Rollback: er is geen aparte rollback per run -- elke rij onder de
   interne klant is per definitie een anonieme-opdrachtgever-vacature, dus
   de rollback sluit ze allemaal in plaats van per run te onderscheiden.
   Haal het client_id op (de query in _get_internal_client_id() hieronder,
   of GET /api/v1/admin/clients?search=anonieme) en draai:
       UPDATE job_orders SET status = 'closed' WHERE client_id = <dat id>;

Weigert te draaien (exitcode 1, niets geschreven) als de interne klant
'GSP Recruitment (anonieme opdrachtgever)' nog niet bestaat -- die rij
wordt aangemaakt door migrations/037_pool_vacancies_consent_sources.py,
dus dit script mag nooit vóór die migratie draaien.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

INTERNAL_CLIENT_NAME = "GSP Recruitment (anonieme opdrachtgever)"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "pool_vacancies.json"

# AdminJobCreate fields (models/schemas.py) this script writes to
# job_orders. `slug` in the JSON is not a job_orders column -- it only
# lets the growth-marketer's content and the frontend address a specific
# seeded vacancy by a stable string instead of a database id.
JOB_FIELDS = (
    "title", "department", "seniority", "location_type", "city",
    "salary_min", "salary_max", "salary_currency", "description",
    "requirements", "nice_to_have", "urgency", "employment_type",
    "sponsorship_possible", "company_display",
)

# Same defaults as AdminJobCreate/JobOrderCreate for a field a JSON row
# happens to omit -- everything else defaults to None (nullable column).
JOB_FIELD_DEFAULTS = {
    "salary_currency": "EUR",
    "urgency": "normal",
    "sponsorship_possible": False,
}


async def _connect():
    import asyncpg
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "recruitment_db"),
        user=os.getenv("POSTGRES_USER", "talentos_write"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


async def _get_internal_client_id(conn) -> int | None:
    row = await conn.fetchrow(
        "SELECT id FROM clients WHERE company_name = $1 AND is_internal = true",
        INTERNAL_CLIENT_NAME,
    )
    return row["id"] if row else None


def _load_vacancies() -> list[dict]:
    with open(DATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


async def run(apply: bool) -> int:
    vacancies = _load_vacancies()
    conn = await _connect()
    try:
        client_id = await _get_internal_client_id(conn)
        if client_id is None:
            print(
                f"REFUSED: interne klant '{INTERNAL_CLIENT_NAME}' bestaat niet -- "
                "draai eerst migrations/037_pool_vacancies_consent_sources.py."
            )
            return 1

        new_count = 0
        existing_count = 0
        for vac in vacancies:
            title = vac["title"]
            seniority = vac.get("seniority")
            existing = await conn.fetchrow(
                "SELECT id FROM job_orders WHERE client_id = $1 AND title = $2 "
                "AND seniority IS NOT DISTINCT FROM $3",
                client_id, title, seniority,
            )
            if existing:
                existing_count += 1
                print(f"bestaat  id={existing['id']:<6} {title!r} ({seniority})")
                continue

            new_count += 1
            if not apply:
                print(f"nieuw    (dry-run) {title!r} ({seniority})")
                continue

            values = [vac.get(f, JOB_FIELD_DEFAULTS.get(f)) for f in JOB_FIELDS]
            placeholders = ", ".join(f"${i + 2}" for i in range(len(JOB_FIELDS)))
            row = await conn.fetchrow(
                f"""INSERT INTO job_orders
                       (client_id, {", ".join(JOB_FIELDS)}, status, is_demo)
                    VALUES ($1, {placeholders}, 'open', false)
                    RETURNING id""",
                client_id, *values,
            )
            print(f"nieuw    id={row['id']:<6} {title!r} ({seniority})")

        mode = "--apply" if apply else "dry-run (pass --apply om te schrijven)"
        print(f"\n{mode}: {new_count} nieuw, {existing_count} bestaat, {len(vacancies)} totaal.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--apply", action="store_true",
        help="Voer de invoer echt uit; zonder deze vlag is dit een dry-run (standaard).",
    )
    args = parser.parse_args()
    return asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    sys.exit(main())
