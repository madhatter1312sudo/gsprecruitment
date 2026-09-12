"""
Talent OS -- WS5 BV10: one shared way for an admin list route to accept a
`sort`/`order` pair without ever letting request input reach `ORDER BY`.

The rule this module enforces is deliberately narrow: a route declares an
allowlist mapping the *public* column name a client may ask for onto the
literal SQL fragment that is safe to interpolate (usually a qualified
column, sometimes an expression). A `sort` value outside that mapping is
a 422, never a fallback to the default, because silently sorting by
something else than what was asked for is the kind of difference that
only shows up as a wrong-looking page much later. `order` is likewise
either "asc" or "desc" and nothing else.

Nothing here builds a WHERE clause and nothing here takes a value: only a
key lookup in a dict the route itself wrote. The returned string is
therefore composed entirely of literals from the calling module.
"""
from typing import Dict, Optional

from fastapi import HTTPException

ORDER_DIRECTIONS = ("asc", "desc")


def resolve_order_by(
    sort: Optional[str],
    order: Optional[str],
    *,
    allowed: Dict[str, str],
    default: str,
    tiebreaker: Optional[str] = None,
) -> str:
    """Return the SQL that goes after `ORDER BY`.

    `allowed` maps a client-visible column name onto a literal SQL
    fragment. `default` is the full fragment used when no `sort` is given
    -- it must reproduce the route's historical ordering exactly, so an
    existing caller that passes neither parameter sees no change at all.
    `tiebreaker` is appended after an explicit sort to keep paging stable
    when the sort column has duplicates.

    Raises 422 for a column outside the allowlist or an `order` that is
    not asc/desc.
    """
    # Unit tests across this codebase call route functions directly rather
    # than through FastAPI, so an untouched `sort`/`order` parameter
    # arrives as the fastapi.Query default object, not as None. Treat
    # anything that is not a string as "not given" -- through the real
    # HTTP path FastAPI has already coerced a present value to str.
    if not isinstance(sort, str):
        sort = None
    if not isinstance(order, str):
        order = None

    if order is not None:
        order_norm = order.strip().lower()
        if order_norm not in ORDER_DIRECTIONS:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_order_direction",
                    "message": "order must be 'asc' or 'desc'.",
                    "allowed": list(ORDER_DIRECTIONS),
                },
            )
    else:
        order_norm = None

    if sort is None or sort == "":
        # order= on its own has no column to apply to; the documented
        # behaviour is that the default ordering stands.
        return default

    column = allowed.get(sort.strip())
    if column is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_sort_column",
                "message": f"sort must be one of: {', '.join(sorted(allowed))}.",
                "allowed": sorted(allowed),
            },
        )

    direction = "DESC" if (order_norm or "asc") == "desc" else "ASC"
    clause = f"{column} {direction}"
    if tiebreaker:
        clause = f"{clause}, {tiebreaker}"
    return clause


def sort_key_for(sort: Optional[str], *, allowed: Dict[str, str], default_key: str) -> str:
    """The dict key a Python-side merge sort should use for the same
    request, for the one list route (GET /api/v1/admin/candidates) that
    merges two SQL branches in Python. Returns the row key, not SQL --
    the allowlist is shared with resolve_order_by() so the two can never
    drift apart, and validation has already happened there."""
    if not isinstance(sort, str) or sort == "":
        return default_key
    return sort.strip()
