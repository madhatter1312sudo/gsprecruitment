"""
Talent OS — One-off migration: move locally-stored CV files into R2.

Historically CVs were written to /app/uploads/cv with plain open() and no
volume mount, so most of what's on disk today is whatever survived since the
last deploy. This script walks that directory, uploads each file to R2 under
cv/{user_id}/{original filename}, and rewrites candidate_profiles/candidates
.cv_file_path to the new R2 key -- matching files to rows by looking up which
row currently references each local filename.

Run on the VPS (where /app/uploads/cv actually has files) after the R2_*
env vars are set:

    python3 migrate_cv_to_r2.py --dry-run     # preview only, no writes
    python3 migrate_cv_to_r2.py               # do it for real
    python3 migrate_cv_to_r2.py --dir /some/other/path

Safe to re-run: a row whose cv_file_path already starts with "cv/" (already
migrated) is skipped.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/backend")

import asyncpg  # noqa: E402

from services import storage  # noqa: E402


CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


async def _connect():
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "recruitment_db"),
        user=os.getenv("POSTGRES_USER", "talentos_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


async def _rows_referencing(conn, filename: str):
    """Find candidate_profiles/candidates rows whose cv_file_path is exactly
    the legacy local path for this file (upload_cv always wrote
    "/uploads/cv/{filename}"), along with the user_id to key the R2 object
    on. Exact match rather than a LIKE '%'||filename pattern -- filename
    comes straight from os.listdir() and could contain '%'/'_', which would
    be interpreted as SQL LIKE wildcards; it also sidesteps re-matching an
    already-migrated row whose R2 key happens to end in the same filename."""
    legacy_path = "/uploads/cv/" + filename
    profile_rows = await conn.fetch(
        """SELECT user_id, cv_file_path FROM candidate_profiles
           WHERE cv_file_path = $1""",
        legacy_path,
    )
    # candidates rows don't carry a user_id directly -- resolve via email.
    candidate_rows = await conn.fetch(
        """SELECT c.id AS candidate_id, c.cv_file_path, u.id AS user_id
           FROM candidates c
           LEFT JOIN users u ON LOWER(u.email) = LOWER(c.email)
           WHERE c.cv_file_path = $1""",
        legacy_path,
    )
    return profile_rows, candidate_rows


async def migrate(directory: str, dry_run: bool) -> None:
    if not storage.is_configured():
        print("R2 is not configured (R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET) "
              "-- set those env vars before running this script.")
        sys.exit(1)

    if not os.path.isdir(directory):
        print(f"Directory not found: {directory}")
        sys.exit(1)

    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    print(f"Found {len(files)} file(s) in {directory}")

    conn = await _connect()
    uploaded = 0
    updated_rows = 0
    unmatched = []
    errors = []

    try:
        for filename in files:
            local_path = os.path.join(directory, filename)
            ext = os.path.splitext(filename)[1].lower()

            profile_rows, candidate_rows = await _rows_referencing(conn, filename)
            if not profile_rows and not candidate_rows:
                unmatched.append(filename)
                continue

            # Skip rows that are already migrated (cv_file_path already
            # starts with "cv/") BEFORE uploading anything -- checked here,
            # ahead of put_object, so a re-run of this script never
            # re-uploads a file it already moved. (_rows_referencing's exact
            # match against the legacy "/uploads/cv/..." path means this
            # should already be empty in practice, but a matched row could
            # in principle have been migrated by a different filename/key
            # scheme, so still worth guarding explicitly.)
            pending_profile_rows = [r for r in profile_rows if not r["cv_file_path"].startswith("cv/")]
            pending_candidate_rows = [r for r in candidate_rows if not r["cv_file_path"].startswith("cv/")]
            if not pending_profile_rows and not pending_candidate_rows:
                print(f"{filename}: already migrated, skipping")
                continue

            # Determine the user_id to key the R2 object under -- prefer a
            # candidate_profiles row (it always has one), else the resolved
            # user_id from the candidates row, else fall back to the
            # candidate_id so the file still ends up somewhere sane.
            user_id = None
            if pending_profile_rows:
                user_id = pending_profile_rows[0]["user_id"]
            elif pending_candidate_rows and pending_candidate_rows[0]["user_id"] is not None:
                user_id = pending_candidate_rows[0]["user_id"]
            elif pending_candidate_rows:
                user_id = pending_candidate_rows[0]["candidate_id"]

            key = storage.cv_key(user_id, ext, os.path.splitext(filename)[0])

            print(f"{'[dry-run] ' if dry_run else ''}{filename} -> {key} "
                  f"({len(pending_profile_rows)} profile row(s), {len(pending_candidate_rows)} candidate row(s))")

            if dry_run:
                continue

            with open(local_path, "rb") as f:
                data = f.read()

            try:
                await storage.put_object(key, data, CONTENT_TYPES.get(ext, "application/octet-stream"))
                uploaded += 1
            except Exception as e:
                errors.append(f"{filename}: upload failed -- {e}")
                continue

            for row in pending_profile_rows:
                await conn.execute(
                    "UPDATE candidate_profiles SET cv_file_path = $1 WHERE user_id = $2",
                    key, row["user_id"],
                )
                updated_rows += 1
            for row in pending_candidate_rows:
                await conn.execute(
                    "UPDATE candidates SET cv_file_path = $1 WHERE id = $2",
                    key, row["candidate_id"],
                )
                updated_rows += 1
    finally:
        await conn.close()

    print("\n--- Summary ---")
    print(f"Files scanned:   {len(files)}")
    print(f"Uploaded to R2:  {uploaded}{' (dry-run, none actually uploaded)' if dry_run else ''}")
    print(f"DB rows updated: {updated_rows}")
    print(f"Unmatched files (no DB row references them): {len(unmatched)}")
    for f in unmatched:
        print(f"  - {f}")
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors:
            print(f"  - {e}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="/app/uploads/cv", help="Local CV directory to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no uploads or DB writes")
    args = parser.parse_args()
    asyncio.run(migrate(args.dir, args.dry_run))


if __name__ == "__main__":
    main()
