"""
Unit tests for WS-E.7 outreach compliance gates (routers/outreach.py
_draft_refusal() and its pure text-check helpers) and the provenance
validation on the candidate-sourcing insert path (models/schemas.py
CandidateSourceCreate, routers/prospects.py ProspectCreate).

No DB/network needed for the pure-text tests; _draft_refusal() is
DB-backed (suppression_list / candidates / client_prospects lookups) so
it's exercised with the same fetch_one/fetch_all-monkeypatch style as
tests/test_gdpr_erasure.py.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from core import privacy
from models.schemas import CandidateCreate, CandidateSourceCreate
from routers.prospects import ProspectCreate, ProspectUpdate


NL_STOP = (
    'U kunt zich afmelden door te antwoorden met "STOP" -- wij verwerken dat binnen 24 uur: '
    'wij verwijderen uw gegevens uit onze actieve bestanden en uw e-mailadres blijft alleen op '
    'een blokkeerlijst zodat wij u niet opnieuw benaderen.'
)
EN_STOP = (
    'You can opt out by replying "STOP" -- we process that within 24 hours: we remove your data '
    'from our active files, and your e-mail address is kept only on a suppression list so we do '
    'not contact you again.'
)
NL_ART14 = (
    "Dit bericht komt van GSP Recruitment (Brainport/Eindhoven), sourcing@gsprecruitment.nl. "
    "Wij vonden uw LinkedIn-profiel via https://linkedin.com/in/x op 2026-08-01 in het kader van "
    "werving voor technische functies. Grondslag: gerechtvaardigd belang bij werving. Wij bewaren "
    "deze gegevens 3 maanden na 2026-08-01 als u niet reageert. U heeft het recht om bezwaar te "
    "maken tegen deze verwerking (art. 21 AVG). " + NL_STOP + " Een klacht over deze verwerking "
    "kunt u indienen bij de Autoriteit Persoonsgegevens (autoriteitpersoonsgegevens.nl)."
)


def _draft(**overrides):
    base = {
        "id": 1,
        "target_type": "candidate",
        "target_id": 10,
        "target_email": "candidate@example.com",
        "job_id": None,
        "presented_candidate_id": None,
        "body": NL_ART14,
        "language": "nl",
    }
    base.update(overrides)
    return base


def _candidate(**overrides):
    """A fully-compliant candidate row for _draft_refusal()'s SELECT --
    override just the field(s) a test cares about."""
    base = {
        "lawful_basis": "gerechtvaardigd_belang",
        "consent_withdrawn_at": None,
        "consent_spec_presentation_at": None,
        "source_url": "https://linkedin.com/in/x",
    }
    base.update(overrides)
    return base


def _prospect(**overrides):
    base = {"lawful_basis": "zakelijk_functioneel_adres", "opt_out_at": None}
    base.update(overrides)
    return base


# ── Pure text-check helpers (no DB) ───────────────────────────────────────

def test_has_optout_line_matches_nl_stop_sentence():
    from routers.outreach import _has_optout_line
    assert _has_optout_line(NL_STOP) is True


def test_has_optout_line_matches_en_stop_sentence():
    from routers.outreach import _has_optout_line
    assert _has_optout_line(EN_STOP) is True


def test_has_optout_line_false_without_stop_sentence():
    from routers.outreach import _has_optout_line
    assert _has_optout_line("Hello, we have a role that might interest you.") is False


def test_has_art14_block_true_for_full_nl_block():
    from routers.outreach import _has_art14_block
    assert _has_art14_block(NL_ART14, "nl") is True


def test_has_art14_block_false_when_ap_complaint_right_missing():
    from routers.outreach import _has_art14_block
    truncated = NL_ART14.replace(
        "Een klacht over deze verwerking kunt u indienen bij de Autoriteit Persoonsgegevens "
        "(autoriteitpersoonsgegevens.nl).", "",
    )
    assert _has_art14_block(truncated, "nl") is False


# ── _draft_refusal() -- stubbed DB, one scenario per refusal code ────────

class _FakeDB:
    def __init__(self, candidate=None, prospect=None, suppressed=False):
        self.candidate = candidate
        self.prospect = prospect
        self.suppressed = suppressed
        self.queries = []

    async def fetch_one(self, sql, *args):
        self.queries.append((sql, args))
        if "FROM suppression_list" in sql:
            return {"suppressed": True} if self.suppressed else None
        if "FROM candidates WHERE id" in sql:
            return self.candidate
        if "FROM client_prospects WHERE id" in sql:
            return self.prospect
        return None


@pytest.fixture()
def patch_db(monkeypatch):
    def _patch(db: _FakeDB):
        import routers.outreach as outreach
        monkeypatch.setattr(outreach, "fetch_one", db.fetch_one)
        return outreach
    return _patch


def test_approve_refuses_missing_optout_line(patch_db):
    outreach = patch_db(_FakeDB())
    draft = _draft(body="Hi, interested in a new role? No opt-out mentioned here.")
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_MISSING_OPTOUT


def test_approve_refuses_missing_art14_block_for_gerechtvaardigd_belang(patch_db):
    outreach = patch_db(_FakeDB(candidate=_candidate()))
    draft = _draft(body=NL_STOP)  # opt-out present, Art. 14 block absent
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_MISSING_ART14


def test_approve_allows_full_nl_block_for_gerechtvaardigd_belang(patch_db):
    outreach = patch_db(_FakeDB(candidate=_candidate()))
    draft = _draft(body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is None


def test_approve_allows_portal_registratie_without_art14_block(patch_db):
    """SOP §3.2: portal_registratie/opt_in_talentpool never carry the
    Art. 14 block -- only the STOP line is required for them. They still
    need a valid lawful_basis + http(s) source_url on file, which is why
    candidate.py's portal-registration insert sets source_url too."""
    outreach = patch_db(_FakeDB(candidate=_candidate(lawful_basis="portal_registratie")))
    draft = _draft(body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is None


def test_approve_refuses_withdrawn_consent(patch_db):
    outreach = patch_db(_FakeDB(candidate=_candidate(consent_withdrawn_at="2026-08-01T00:00:00Z")))
    draft = _draft(body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_RECIPIENT_OPTED_OUT


def test_approve_refuses_suppressed_recipient(patch_db):
    outreach = patch_db(_FakeDB(suppressed=True))
    draft = _draft(body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_RECIPIENT_SUPPRESSED


def test_approve_refuses_missing_candidate_row(patch_db):
    outreach = patch_db(_FakeDB(candidate=None))
    draft = _draft(body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_CANDIDATE_NOT_FOUND


def test_approve_refuses_unknown_target_type(patch_db):
    outreach = patch_db(_FakeDB())
    draft = _draft(target_type="carrier_pigeon", body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_UNKNOWN_TARGET_TYPE


def test_approve_refuses_candidate_with_null_lawful_basis(patch_db):
    outreach = patch_db(_FakeDB(candidate=_candidate(lawful_basis=None)))
    draft = _draft(body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_CANDIDATE_MISSING_PROVENANCE


def test_approve_refuses_candidate_with_non_http_source_url(patch_db):
    outreach = patch_db(_FakeDB(candidate=_candidate(source_url="apollo:12345")))
    draft = _draft(body=NL_ART14)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_CANDIDATE_MISSING_PROVENANCE


def test_approve_refuses_prospect_without_lawful_basis(patch_db):
    outreach = patch_db(_FakeDB(prospect=_prospect(lawful_basis=None)))
    draft = _draft(target_type="client_prospect", target_id=5, body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_PROSPECT_NO_LAWFUL_BASIS


def test_approve_refuses_prospect_who_opted_out(patch_db):
    outreach = patch_db(_FakeDB(prospect=_prospect(opt_out_at="2026-08-01T00:00:00Z")))
    draft = _draft(target_type="client_prospect", target_id=5, body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_RECIPIENT_OPTED_OUT


def test_approve_allows_prospect_with_lawful_basis(patch_db):
    outreach = patch_db(_FakeDB(prospect=_prospect()))
    draft = _draft(target_type="client_prospect", target_id=5, body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is None


def test_approve_refuses_spec_candidate_without_presentation_consent(patch_db):
    outreach = patch_db(_FakeDB(
        prospect=_prospect(lawful_basis="opt_in"),
        candidate={"consent_spec_presentation_at": None},
    ))
    draft = _draft(target_type="client_prospect", target_id=5, presented_candidate_id=99, body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is not None
    status_code, code, _detail = result
    assert (status_code, code) == outreach.REFUSAL_CANDIDATE_NO_SPEC_CONSENT


def test_approve_allows_spec_candidate_with_presentation_consent(patch_db):
    outreach = patch_db(_FakeDB(
        prospect=_prospect(lawful_basis="opt_in"),
        candidate={"consent_spec_presentation_at": "2026-08-01T00:00:00Z"},
    ))
    draft = _draft(target_type="client_prospect", target_id=5, presented_candidate_id=99, body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is None


def test_approve_spec_candidate_check_no_longer_reads_job_id(patch_db):
    """L2 regression guard: job_id must NOT be treated as the presented
    candidate any more -- only presented_candidate_id counts."""
    outreach = patch_db(_FakeDB(prospect=_prospect(lawful_basis="opt_in")))
    draft = _draft(target_type="client_prospect", target_id=5, job_id=99, presented_candidate_id=None, body=NL_STOP)
    result = asyncio.run(outreach._draft_refusal(draft))
    assert result is None


# ── Provenance validation on the create paths (models/schemas.py) ────────

def test_candidate_source_create_requires_source_url():
    with pytest.raises(ValidationError):
        CandidateSourceCreate(full_name="A Person", lawful_basis="gerechtvaardigd_belang")


def test_candidate_source_create_rejects_non_http_source_url():
    with pytest.raises(ValidationError):
        CandidateSourceCreate(
            full_name="A Person",
            lawful_basis="gerechtvaardigd_belang",
            source_url="javascript:alert(1)",
        )


def test_candidate_source_create_accepts_valid_https_source_url():
    c = CandidateSourceCreate(
        full_name="A Person",
        lawful_basis="gerechtvaardigd_belang",
        source_url="https://linkedin.com/in/a-person",
    )
    assert c.source_url == "https://linkedin.com/in/a-person"
    assert c.date_found is not None  # defaulted


def test_candidate_source_create_rejects_bad_lawful_basis():
    with pytest.raises(ValidationError):
        CandidateSourceCreate(
            full_name="A Person",
            source_url="https://linkedin.com/in/a-person",
            lawful_basis="not_a_real_basis",
        )


def test_candidate_create_still_optional_for_legacy_apollo_rows():
    """CandidateResponse subclasses CandidateCreate directly -- Apollo-pool
    rows have no source_url/lawful_basis at all (source_url is literally
    'apollo:<id>', not an http URL) and must still deserialize."""
    c = CandidateCreate(full_name="Legacy Apollo Row", source_url="apollo:12345")
    assert c.source_url == "apollo:12345"
    assert c.lawful_basis is None


def test_prospect_create_requires_lawful_basis():
    with pytest.raises(ValidationError):
        ProspectCreate(company="Acme BV")


def test_prospect_create_rejects_bad_lawful_basis():
    with pytest.raises(ValidationError):
        ProspectCreate(company="Acme BV", lawful_basis="made_up_value")


def test_prospect_create_accepts_valid_lawful_basis():
    p = ProspectCreate(company="Acme BV", lawful_basis="bestaande_relatie")
    assert p.lawful_basis == "bestaande_relatie"


def test_prospect_create_rejects_non_http_source_url():
    with pytest.raises(ValidationError):
        ProspectCreate(company="Acme BV", lawful_basis="bestaande_relatie", source_url="javascript:alert(1)")


def test_prospect_create_accepts_valid_https_source_url():
    p = ProspectCreate(
        company="Acme BV", lawful_basis="bestaande_relatie",
        source_url="https://acme.example/careers",
    )
    assert p.source_url == "https://acme.example/careers"


def test_prospect_create_source_url_optional():
    p = ProspectCreate(company="Acme BV", lawful_basis="bestaande_relatie")
    assert p.source_url is None


def test_prospect_update_can_set_lawful_basis():
    u = ProspectUpdate(lawful_basis="opt_in")
    assert u.lawful_basis == "opt_in"


def test_prospect_update_rejects_bad_lawful_basis():
    with pytest.raises(ValidationError):
        ProspectUpdate(lawful_basis="not_a_real_value")


def test_prospect_update_can_set_source_url():
    u = ProspectUpdate(source_url="https://acme.example/careers")
    assert u.source_url == "https://acme.example/careers"


def test_prospect_update_rejects_non_http_source_url():
    with pytest.raises(ValidationError):
        ProspectUpdate(source_url="javascript:alert(1)")


# ── Suppression hashing (mirrors routers/gdpr.py add_suppression) ────────

def test_suppression_hash_matches_privacy_module():
    assert privacy.email_hash("STOP-sender@Example.com") == privacy.email_hash("stop-sender@example.com")


def test_suppression_domain_extraction():
    assert privacy.email_domain("someone@bigcorp.nl") == "bigcorp.nl"
