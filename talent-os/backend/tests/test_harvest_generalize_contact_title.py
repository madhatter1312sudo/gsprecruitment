"""
Security-audit follow-up (finding 5): services/harvest.py sent
company_name + the prospect's exact contact_title + industry to OpenRouter,
a combination that can identify a single person at a small company.
_generalize_contact_title() collapses the title into a broad category.

Pure function, no DB/network needed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

from services.harvest import _generalize_contact_title


def test_ceo_and_founder_titles_map_to_senior_executive():
    assert _generalize_contact_title("CEO") == "senior executive"
    assert _generalize_contact_title("Founder & Managing Director") == "senior executive"
    assert _generalize_contact_title("Oprichter") == "senior executive"


def test_cto_maps_to_senior_executive_not_engineering():
    # A specific "CTO" is exactly the audit's example ("CTO at a 40-person
    # SME") -- it must not survive as a distinct, more granular category.
    assert _generalize_contact_title("CTO") == "senior executive"


def test_engineering_titles_map_to_engineering_leadership():
    assert _generalize_contact_title("Head of Engineering") == "engineering leadership"
    assert _generalize_contact_title("VP Product Development") == "engineering leadership"


def test_hr_titles_map_to_hr_talent_leadership():
    assert _generalize_contact_title("Talent Acquisition Lead") == "HR/talent leadership"


def test_unknown_or_missing_title_falls_back_to_generic_category():
    assert _generalize_contact_title("Regional Sales Coordinator") == "hiring manager"
    assert _generalize_contact_title(None) == "hiring manager"
    assert _generalize_contact_title("") == "hiring manager"


def test_never_returns_the_raw_specific_title():
    for title in ("CTO", "Chief Executive Officer", "Head of Engineering",
                  "HR Business Partner", "Something Unusual"):
        out = _generalize_contact_title(title)
        assert out != title
