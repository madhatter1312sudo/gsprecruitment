#!/usr/bin/env python3
"""
Talent OS — compare two `pg_dump --schema-only` outputs for structural
convergence (WS-C.1 schema-alignment follow-up).

Normalises each dump to two sets:
  - table.column pairs, from every `CREATE TABLE ... ( ... )` block
    (ALTER TABLE ... ADD COLUMN statements are also picked up, so a dump
    that expresses a column via an ALTER rather than inline in the CREATE
    TABLE, which pg_dump does for some columns, still counts).
  - index names, from every `CREATE [UNIQUE] INDEX <name> ON` statement.

Then diffs those sets between the two dumps and prints anything only on
one side. Exits 0 if both sets are identical, 1 otherwise -- usable as a
CI gate as well as a one-off convergence proof.

Deliberately ignores: column types/defaults/constraints, table/column
comments, ownership, sequences, and statement ordering -- this is a
structural (which tables/columns/indexes exist) comparison, not a byte-
for-byte one. That's the right granularity for "did migrations reproduce
production's shape", not "is every type identical" (see
migrations/019_prod_schema_alignment.py's docstring for known type-level
divergences, e.g. TIMESTAMPTZ vs `timestamp without time zone`, that are
intentionally out of scope here).

Usage:
    python3 scripts/compare_schema.py dump_a.sql dump_b.sql
"""
import re
import sys

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(?:public\.)?\"?(\w+)\"?\s*\((.*?)\n\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_ADD_COLUMN_RE = re.compile(
    r"ALTER TABLE(?:\s+ONLY)?\s+(?:public\.)?\"?(\w+)\"?\s+"
    r"ADD COLUMN(?:\s+IF NOT EXISTS)?\s+\"?(\w+)\"?",
    re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"CREATE(?:\s+UNIQUE)?\s+INDEX(?:\s+IF NOT EXISTS)?\s+\"?(\w+)\"?\s+ON",
    re.IGNORECASE,
)

# Lines inside a CREATE TABLE(...) body that are not columns.
_NON_COLUMN_LINE = re.compile(
    r"^(CONSTRAINT|UNIQUE\s*\(|PRIMARY KEY\s*\(|FOREIGN KEY|CHECK\s*\()",
    re.IGNORECASE,
)


def _strip_comment_lines(text: str) -> str:
    return "\n".join(
        line for line in text.split("\n") if not line.strip().startswith("--")
    )


def parse_dump(sql: str):
    """Return (set of 'table.column', set of index names)."""
    sql = _strip_comment_lines(sql)
    columns = set()
    tables = set()

    for m in _CREATE_TABLE_RE.finditer(sql):
        table = m.group(1).lower()
        tables.add(table)
        body = m.group(2)
        for raw_line in body.split("\n"):
            line = raw_line.strip().rstrip(",")
            if not line or _NON_COLUMN_LINE.match(line):
                continue
            col = line.split()[0].strip('"').lower()
            if col:
                columns.add(f"{table}.{col}")

    for m in _ALTER_ADD_COLUMN_RE.finditer(sql):
        table, col = m.group(1).lower(), m.group(2).lower()
        columns.add(f"{table}.{col}")

    indexes = {m.group(1).lower() for m in _CREATE_INDEX_RE.finditer(sql)}

    return columns, indexes


def main():
    if len(sys.argv) != 3:
        print("usage: compare_schema.py <dump_a.sql> <dump_b.sql>", file=sys.stderr)
        return 2

    path_a, path_b = sys.argv[1], sys.argv[2]
    with open(path_a, encoding="utf-8") as fh:
        cols_a, idx_a = parse_dump(fh.read())
    with open(path_b, encoding="utf-8") as fh:
        cols_b, idx_b = parse_dump(fh.read())

    only_a_cols = sorted(cols_a - cols_b)
    only_b_cols = sorted(cols_b - cols_a)
    only_a_idx = sorted(idx_a - idx_b)
    only_b_idx = sorted(idx_b - idx_a)

    ok = not (only_a_cols or only_b_cols or only_a_idx or only_b_idx)

    print(f"{path_a}: {len(cols_a)} columns, {len(idx_a)} indexes")
    print(f"{path_b}: {len(cols_b)} columns, {len(idx_b)} indexes")

    if only_a_cols:
        print(f"\nColumns only in {path_a}:")
        for c in only_a_cols:
            print(f"  {c}")
    if only_b_cols:
        print(f"\nColumns only in {path_b}:")
        for c in only_b_cols:
            print(f"  {c}")
    if only_a_idx:
        print(f"\nIndexes only in {path_a}:")
        for i in only_a_idx:
            print(f"  {i}")
    if only_b_idx:
        print(f"\nIndexes only in {path_b}:")
        for i in only_b_idx:
            print(f"  {i}")

    if ok:
        print("\nCONVERGED: identical table.column and index-name sets.")
        return 0
    else:
        print("\nDIVERGED: see differences above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
