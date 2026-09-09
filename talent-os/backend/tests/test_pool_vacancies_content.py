"""
Structural test for talent-os/backend/data/pool_vacancies.json (WS-4,
growth-marketer deliverable, seeded by scripts/seed_pool_vacancies.py --
see that script's docstring). Pure static checks, no DB needed.

This file is not written by backend-dev: it's the parallel growth-marketer
track's content. If it doesn't exist yet in this worktree, every test here
is skipped (not failed) rather than asserting on content nobody has
written -- once the file lands, these tests hold it to the content
contract from docs/VERWERKINGSREGISTER.md §6 punt 11 / docs/SOURCING-
SOP.md §1.5: 27 rows, unique (title, seniority) and slug, a mandatory
closing paragraph per description, no forbidden phrasing that would
suggest a concrete, named opdrachtgever, employment_type in the three
allowed values, sponsorship_possible always false, company_display always
null, and salary_min <= salary_max wherever both are set.
"""
import json
import os

import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BACKEND_ROOT, "data", "pool_vacancies.json")

if not os.path.exists(DATA_PATH):
    pytest.skip(
        f"{DATA_PATH} does not exist yet (growth-marketer's parallel deliverable) -- "
        "skipping content checks until it lands.",
        allow_module_level=True,
    )

with open(DATA_PATH, encoding="utf-8") as _fh:
    VACANCIES = json.load(_fh)

EXPECTED_COUNT = 27
ALLOWED_EMPLOYMENT_TYPES = {"vast", "detachering", "interim"}

# Words/phrases that would suggest a concrete, real, currently-running
# assignment with a named opdrachtgever -- the exact risk the owner
# accepted only under the mitigation that no text implies one (Wet OHP /
# ABU-NBBU-gedragscode / doelbinding, VERWERKINGSREGISTER.md §6 punt 11).
FORBIDDEN_WORDS = [
    "onze klant",  # "our client" -- implies a real, specific principal
    "onze opdrachtgever",
    "wij zoeken voor",  # "we are looking [for our client]"
    "op korte termijn starten bij",  # implies a concrete, imminent placement
]

# A closing paragraph must exist and read as an honest, faceless
# disclosure -- not a strict wording match (copy is the growth-marketer's
# call), but it must mention that GSP itself is behind the vacancy without
# naming a company.
CLOSING_PARAGRAPH_MARKERS = ("GSP", "opdrachtgever")


def test_pool_vacancies_has_exactly_27_rows():
    assert len(VACANCIES) == EXPECTED_COUNT


def test_pool_vacancies_title_and_seniority_pairs_are_unique():
    pairs = [(v["title"], v.get("seniority")) for v in VACANCIES]
    assert len(pairs) == len(set(pairs)), "duplicate (title, seniority) pair(s) found"


def test_pool_vacancies_slugs_are_unique_and_present():
    slugs = [v.get("slug") for v in VACANCIES]
    assert all(slugs), "every row must have a non-empty slug"
    assert len(slugs) == len(set(slugs)), "duplicate slug(s) found"


def test_pool_vacancies_have_no_client_id_or_status():
    """seed_pool_vacancies.py supplies client_id (the internal anonymous
    client) and status ('open') itself -- the JSON must not pre-empt
    either, per the shared contract."""
    for v in VACANCIES:
        assert "client_id" not in v
        assert "status" not in v


@pytest.mark.parametrize("index", range(len(VACANCIES)))
def test_pool_vacancy_description_has_a_mandatory_closing_paragraph(index):
    v = VACANCIES[index]
    description = v.get("description") or ""
    assert description, f"{v.get('slug')}: description must not be empty"
    # The closing paragraph is the last non-empty block, separated by a
    # blank line (or the whole description if it's a single block).
    paragraphs = [p.strip() for p in description.split("\n\n") if p.strip()]
    assert paragraphs, f"{v.get('slug')}: description has no paragraphs"
    closing = paragraphs[-1]
    assert any(marker in closing for marker in CLOSING_PARAGRAPH_MARKERS), (
        f"{v.get('slug')}: closing paragraph does not read as GSP's own honest "
        f"disclosure (expected one of {CLOSING_PARAGRAPH_MARKERS} in the last "
        f"paragraph): {closing!r}"
    )


@pytest.mark.parametrize("index", range(len(VACANCIES)))
def test_pool_vacancy_text_avoids_forbidden_named_opdrachtgever_phrasing(index):
    v = VACANCIES[index]
    haystack = " ".join(
        str(v.get(field) or "") for field in ("title", "description", "requirements", "nice_to_have")
    ).lower()
    for phrase in FORBIDDEN_WORDS:
        assert phrase not in haystack, f"{v.get('slug')}: forbidden phrase {phrase!r} found"


def test_pool_vacancies_employment_type_is_one_of_the_three_allowed_values():
    for v in VACANCIES:
        assert v.get("employment_type") in ALLOWED_EMPLOYMENT_TYPES, (
            f"{v.get('slug')}: employment_type={v.get('employment_type')!r}"
        )


def test_pool_vacancies_sponsorship_possible_is_always_false():
    """These are anonymous-opdrachtgever pool vacancies GSP posts for
    itself -- sponsorship for a kennismigrant runs via a real, named
    client and the backoffice-partner relationship, never through this
    pool."""
    for v in VACANCIES:
        assert v.get("sponsorship_possible") is False, f"{v.get('slug')}: sponsorship_possible must be false"


def test_pool_vacancies_company_display_is_always_null():
    for v in VACANCIES:
        assert v.get("company_display") is None, f"{v.get('slug')}: company_display must be null"


def test_pool_vacancies_salary_min_never_exceeds_salary_max():
    for v in VACANCIES:
        lo, hi = v.get("salary_min"), v.get("salary_max")
        if lo is not None and hi is not None:
            assert lo <= hi, f"{v.get('slug')}: salary_min {lo} > salary_max {hi}"
