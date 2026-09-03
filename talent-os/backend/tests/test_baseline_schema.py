"""
Talent OS -- WS-C.1 schema self-consistency check.

Pure static analysis, no database required: loads every migrations/0*.py
module's MIGRATION_SQL (000_baseline.py through 014), reconstructs the
resulting table/column map the same way migrations/_runner.py applies it
(splitting on a literal ";", exactly like production does), and then
greps routers/services/tasks for the SQL they actually run against that
schema -- `FROM <table>` / `JOIN <table>` (does the table exist at all)
and literal `INSERT INTO <table> (col1, col2, ...)` column lists (do
those columns exist on that table). Anything referenced that the combined
migrations never create is listed by name so it's obvious what's missing,
rather than only failing at runtime the first time that code path runs.

This does NOT replace scripts/verify_schema_baseline.sh, which is the
real proof: `docker compose up` a throwaway postgres, run every migration
against it for real, and print `\\dt`/`\\d`. This test only catches
"the code and the migrations disagree" without needing postgres at all,
so it can run in the fast unit-test suite alongside test_auth_primitives.py.

Known limitations (by design, not bugs): dynamic column lists built at
runtime from a Python allow-list (e.g. routers/candidates.py's
update_candidate PATCH, which builds `SET {col} = $n` from a hardcoded
`allowed_fields` set rather than a single literal SQL string) are not
parsed here -- there is no fixed `INSERT INTO ... (...)` or
`UPDATE ... SET col = ...` literal to regex out. Those are covered by
this test only at the table level (the table must exist); trust the
route's own `allowed_fields` set as the column-level source of truth.
Column droppable via `SELECT *` is likewise not checked (nothing to
mismatch against). `WITH combined AS (...)` in routers/admin.py's
_CANDIDATES_UNION_CTE defines a `combined` name that this test also
special-cases as non-a-table (a CTE, not something migrations create).
"""
import importlib.util
import os
import re
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_ROOT, "migrations")

# CTE names / non-table identifiers that legitimately follow FROM/JOIN in
# the code but are never created by a migration.
NON_TABLE_NAMES = {
    "combined",          # routers/admin.py's _CANDIDATES_UNION_CTE: WITH combined AS (...)
    "information_schema",  # routers/outreach.py's "SELECT ... FROM information_schema.columns"
    "lateral",           # "... FROM LATERAL (...)" (LATERAL join, not a table)
    "unnest",            # "... FROM unnest(...)" (a set-returning function, not a table)
    "onto",              # false-positive match: prose in services/harvest.py comments
                          # ("a LEFT JOIN onto matches") -- capitalized "JOIN" as an English
                          # word inside a code comment, not SQL.
}


def _load_migration_sql_files():
    """Import every migrations/0*.py in filename order (000 first) and
    return their MIGRATION_SQL strings, in that order -- the same order
    migrations/_runner.py / the deploy workflow apply them in."""
    files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if re.match(r"^\d{3}_.*\.py$", f)
    )
    sqls = []
    for fname in files:
        path = os.path.join(MIGRATIONS_DIR, fname)
        spec = importlib.util.spec_from_file_location(f"_migration_{fname}", path)
        mod = importlib.util.module_from_spec(spec)
        # migrations import `from _runner import run_migration` relative
        # to their own directory -- make sure that resolves the same way
        # the migration files themselves do (sys.path.insert(0, dirname)).
        sys.path.insert(0, MIGRATIONS_DIR)
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(MIGRATIONS_DIR)
        # 003_schema_migrations_tracking.py only bootstraps the
        # schema_migrations bookkeeping table (via ensure_schema_migrations_
        # table() in _runner.py) and back-registers 001/002 -- it has no
        # MIGRATION_SQL of its own to contribute here.
        sql = getattr(mod, "MIGRATION_SQL", "")
        sqls.append((fname, sql))
    return sqls


_COL_LINE_SKIP = re.compile(
    r"^(CONSTRAINT|UNIQUE\s*\(|PRIMARY KEY\s*\(|FOREIGN KEY|CHECK\s*\()",
    re.IGNORECASE,
)


def _strip_sql_comment_lines(stmt: str) -> str:
    """migrations/_runner.py splits each migration's SQL on a literal ";",
    so a leading `-- some comment\nCREATE TABLE ...` block-comment header
    ends up glued onto the front of the next real statement (there's no
    semicolon between them). Drop full-line comments before parsing."""
    return "\n".join(
        line for line in stmt.split("\n") if not line.strip().startswith("--")
    )


def _parse_create_table(stmt: str):
    """Given a single `CREATE TABLE IF NOT EXISTS name ( ... )` statement
    (semicolon already stripped by the caller, comment lines stripped),
    return (table, {cols})."""
    m = re.match(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)\s*\((.*)\)\s*$",
        _strip_sql_comment_lines(stmt).strip(), re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    table, body = m.group(1), m.group(2)
    cols = set()
    for raw_line in body.split("\n"):
        line = raw_line.strip().rstrip(",")
        if not line or _COL_LINE_SKIP.match(line):
            continue
        col = line.split()[0]
        cols.add(col.lower())
    return table.lower(), cols


def _parse_alter_add_columns(stmt: str):
    """Given a single `ALTER TABLE name ADD COLUMN IF NOT EXISTS col ...
    [, ADD COLUMN IF NOT EXISTS col2 ...]` statement, return (table, {cols})."""
    m = re.match(
        r"ALTER TABLE\s+(\w+)\s+(.*)$",
        _strip_sql_comment_lines(stmt).strip(), re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    table, rest = m.group(1), m.group(2)
    cols = {
        c.lower()
        for c in re.findall(r"ADD COLUMN(?:\s+IF NOT EXISTS)?\s+(\w+)", rest, re.IGNORECASE)
    }
    if not cols:
        return None
    return table.lower(), cols


def build_known_schema():
    """table_name -> set(column_names), from every migration's MIGRATION_SQL,
    applied in the same order and split the same way (naive split on a
    literal ";") that migrations/_runner.py uses in production."""
    schema: dict[str, set[str]] = {}
    for fname, sql in _load_migration_sql_files():
        for raw_stmt in sql.split(";"):
            stmt = raw_stmt.strip()
            # A fragment that STARTS with a comment (e.g. a section-header
            # `-- ── clients ──\nCREATE TABLE ...` with no semicolon
            # between them) still has real SQL after the comment lines --
            # only skip it if nothing but comments/whitespace remains.
            if not _strip_sql_comment_lines(stmt).strip():
                continue
            created = _parse_create_table(stmt)
            if created:
                table, cols = created
                schema.setdefault(table, set()).update(cols)
                continue
            altered = _parse_alter_add_columns(stmt)
            if altered:
                table, cols = altered
                # ALTER TABLE on a table this test hasn't seen CREATE TABLE
                # for yet would be a real ordering bug -- surface it loudly
                # rather than silently inventing the table.
                assert table in schema, (
                    f"{fname}: ALTER TABLE {table} ADD COLUMN runs before "
                    f"any CREATE TABLE {table} in migration order"
                )
                schema[table].update(cols)
    return schema


# Deliberately case-sensitive, matching only upper-case SQL keywords: this
# codebase consistently writes SQL in raw/triple-quoted strings with
# UPPERCASE keywords (SELECT, FROM, INSERT INTO, ...), so a case-sensitive
# match finds real SQL without also matching Python's own lowercase
# `from x import y` / `import x` statements throughout every file.
_INSERT_RE = re.compile(r"INSERT INTO\s+(\w+)\s*\(([^)]*)\)")
_FROM_JOIN_RE = re.compile(r"\b(?:FROM|JOIN)\s+(\w+)")


def _iter_source_files():
    for sub in ("routers", "services", "tasks"):
        d = os.path.join(BACKEND_ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if fname.endswith(".py"):
                yield os.path.join(d, fname)


def collect_table_references():
    """path -> set(table names) referenced via FROM/JOIN across the code,
    excluding known non-table identifiers (CTE names etc.)."""
    refs: dict[str, set[str]] = {}
    for path in _iter_source_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        found = {m.lower() for m in _FROM_JOIN_RE.findall(text)} - NON_TABLE_NAMES
        # SQL keywords that can legitimately follow FROM in a non-table
        # context (e.g. "SELECT ... FROM (SELECT ...)") aren't captured
        # by \w+ after FROM/JOIN as bare words here, so no extra filtering
        # needed beyond NON_TABLE_NAMES.
        if found:
            refs[path] = found
    return refs


def collect_insert_column_lists():
    """path -> [(table, [columns])] for every literal INSERT INTO t (...)
    found in the code (multi-line column lists included)."""
    inserts: dict[str, list] = {}
    for path in _iter_source_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        matches = []
        for m in _INSERT_RE.finditer(text):
            table = m.group(1).lower()
            cols = [c.strip().lower() for c in m.group(2).split(",") if c.strip()]
            matches.append((table, cols))
        if matches:
            inserts[path] = matches
    return inserts


def test_every_referenced_table_exists_in_the_combined_migrations():
    schema = build_known_schema()
    refs = collect_table_references()

    misses = []
    for path, tables in refs.items():
        for table in tables:
            if table not in schema:
                misses.append(f"{os.path.relpath(path, BACKEND_ROOT)}: references unknown table '{table}'")

    assert not misses, "Tables referenced in code but never created by any migration:\n" + "\n".join(misses)


def test_every_literal_insert_column_exists_on_its_table():
    schema = build_known_schema()
    inserts = collect_insert_column_lists()

    misses = []
    for path, rows in inserts.items():
        for table, cols in rows:
            if table not in schema:
                # Already reported by the table-existence test above --
                # don't double-report every column here too.
                continue
            for col in cols:
                if col not in schema[table]:
                    misses.append(
                        f"{os.path.relpath(path, BACKEND_ROOT)}: INSERT INTO {table} "
                        f"references unknown column '{col}'"
                    )

    assert not misses, "Columns referenced in an INSERT but never created by any migration:\n" + "\n".join(misses)


def test_baseline_creates_every_table_the_masterplan_flagged_missing():
    """MASTERPLAN-2026.md §2 "Backend": migrations 001-014 never CREATE
    candidates, job_orders, clients, matches, outreach_messages,
    salary_benchmarks, hiring_signals, skill_gaps, data_subject_requests.
    000_baseline.py must be the one that does."""
    schema = build_known_schema()
    required = {
        "candidates", "job_orders", "clients", "matches", "outreach_messages",
        "outreach_campaigns", "salary_benchmarks", "hiring_signals",
        "skill_gaps", "data_subject_requests",
    }
    missing = required - schema.keys()
    assert not missing, f"Baseline is missing required tables: {sorted(missing)}"


def test_matches_has_a_unique_index_for_the_on_conflict_upsert():
    """routers/matches.py does `INSERT INTO matches (...) ON CONFLICT
    (candidate_id, job_id) DO UPDATE ...` -- that target needs a matching
    unique index/constraint or the upsert raises at runtime."""
    for fname, sql in _load_migration_sql_files():
        if fname == "000_baseline.py":
            assert "UNIQUE (candidate_id, job_id)" in sql or "UNIQUE(candidate_id, job_id)" in sql, (
                "matches table must have a UNIQUE(candidate_id, job_id) constraint "
                "for routers/matches.py's ON CONFLICT (candidate_id, job_id) upserts"
            )
            return
    raise AssertionError("000_baseline.py not found")


def _get_baseline_sql() -> str:
    for fname, sql in _load_migration_sql_files():
        if fname == "000_baseline.py":
            return sql
    raise AssertionError("000_baseline.py not found")


# Names migrations/006_drop_redundant_indexes.py deliberately DROPs
# (superseded by composite/duplicate indexes migrations/005 already
# creates). Regression guard for the code-review finding on WS-C.1:
# 000_baseline.py had briefly recreated one of these plus a brand-new
# `CREATE UNIQUE INDEX ... idx_salary_benchmarks_natural_key` that ran
# unconditionally against production's already-existing, already-seeded
# salary_benchmarks table -- failing outright on duplicate rows from a
# repeated migrations/009 seed and aborting every deploy. Any unique
# index belongs in its own migration (see
# migrations/015_salary_benchmarks_natural_key.py), not in the structural
# baseline, which must stay safe to run against a live, already-populated
# production database with no assumptions about the shape of existing
# data.
_DROPPED_BY_006 = {"idx_salary_benchmarks_role", "idx_matches_candidate"}


def test_baseline_creates_no_unique_indexes():
    """000_baseline.py must stay strictly structural: no CREATE UNIQUE
    INDEX statement of its own. A unique index/constraint can fail
    outright against existing, already-populated production data (unlike
    every other statement in this file, which is a plain CREATE TABLE/
    INDEX IF NOT EXISTS or ADD COLUMN IF NOT EXISTS -- safe no-ops on a
    table/column that's already there). Any future unique index belongs
    in its own dedicated migration, applied after 000, that can dedupe
    first if the table might already hold data."""
    sql = _get_baseline_sql()
    assert "CREATE UNIQUE INDEX" not in sql.upper(), (
        "000_baseline.py must not create any unique index directly -- "
        "put it in its own migration (dedupe first if the table could "
        "already have data), applied after 000. See "
        "migrations/015_salary_benchmarks_natural_key.py for the pattern."
    )


def test_baseline_does_not_recreate_indexes_006_drops():
    """000_baseline.py must not CREATE any index that
    migrations/006_drop_redundant_indexes.py deliberately DROPs
    (idx_salary_benchmarks_role, idx_matches_candidate) -- recreating one
    in 000 would just have 006 delete it again on every fresh deploy, and
    reintroduces the exact redundant-index cost 006 was written to
    remove."""
    sql = _get_baseline_sql()
    # Match only an actual `CREATE INDEX ... <name> ON` statement creating
    # that exact index name -- not a bare substring match, which would
    # also fire on this file's own explanatory prose (e.g. "No
    # idx_matches_candidate here: ...") that deliberately mentions these
    # names to document why they're absent.
    created_index_names = set(
        re.findall(r"CREATE(?:\s+UNIQUE)?\s+INDEX(?:\s+IF NOT EXISTS)?\s+(\w+)\s+ON", sql, re.IGNORECASE)
    )
    hits = sorted(_DROPPED_BY_006 & created_index_names)
    assert not hits, (
        f"000_baseline.py recreates {hits}, which migrations/006_drop_"
        f"redundant_indexes.py deliberately drops"
    )
