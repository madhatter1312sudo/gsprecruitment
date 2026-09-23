"""
chief-of-staff FIX FIRST (retention-kolommen branch, finding 3): pure
unit tests for the `.email`-strip validators added to CandidateCreate
(models/schemas.py) and ProspectCreate (routers/prospects.py) -- the two
pydantic-validated create paths behind POST /api/candidates and
POST /api/v1/admin/prospects. No DB needed: these validators run at
model-construction time, before any SQL is issued.

routers/webhook.py's candidate_found action bypasses these models
entirely (its `data` is a raw dict) and is covered separately in
tests/test_ws_c3b_backend_fixes.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

from models.schemas import CandidateCreate
from routers.prospects import ProspectCreate


def test_candidate_create_strips_leading_and_trailing_whitespace():
    c = CandidateCreate(full_name="Padded Candidate", email="  pad-cand@example.com\t")
    assert c.email == "pad-cand@example.com"


def test_candidate_create_email_none_stays_none():
    c = CandidateCreate(full_name="No Email Candidate", email=None)
    assert c.email is None


def test_candidate_create_whitespace_only_email_becomes_none():
    c = CandidateCreate(full_name="Blank Email Candidate", email="   ")
    assert c.email is None


def test_candidate_create_clean_email_is_unaffected():
    c = CandidateCreate(full_name="Clean Candidate", email="clean@example.com")
    assert c.email == "clean@example.com"


def test_prospect_create_strips_leading_and_trailing_whitespace():
    p = ProspectCreate(
        company="Padded Prospect Co", email=" pad-prospect@example.com ",
        lawful_basis="zakelijk_functioneel_adres",
    )
    assert p.email == "pad-prospect@example.com"


def test_prospect_create_email_none_stays_none():
    p = ProspectCreate(company="No Email Prospect Co", lawful_basis="zakelijk_functioneel_adres")
    assert p.email is None


def test_prospect_create_whitespace_only_email_becomes_none():
    p = ProspectCreate(
        company="Blank Email Prospect Co", email="   ",
        lawful_basis="zakelijk_functioneel_adres",
    )
    assert p.email is None
