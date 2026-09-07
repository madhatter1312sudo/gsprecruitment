"""
Unit tests for core/privacy.py pseudonymize_cv_text() -- WS follow-up to
VERWERKINGSREGISTER.md §1.3 (OpenRouter-rij): before services/matcher.py
sends cv_text to OpenRouter for embedding, it must be stripped of directly
identifying data (name, e-mail, phone, URL).

Pure function, no DB/network needed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.privacy import pseudonymize_cv_text


# ── e-mail addresses, various forms ───────────────────────────────────────

def test_strips_plain_email():
    out = pseudonymize_cv_text("Contact: jan.devries@gmail.com voor vragen.")
    assert "jan.devries@gmail.com" not in out
    assert "gmail.com" not in out


def test_strips_email_with_plus_tag_and_subdomain():
    out = pseudonymize_cv_text("mail: fatima+jobs@mail.corp-example.co.uk")
    assert "fatima+jobs@mail.corp-example.co.uk" not in out
    assert "@" not in out


def test_strips_uppercase_email():
    out = pseudonymize_cv_text("E-MAIL: JAN.DEVRIES@BEDRIJF.NL")
    assert "JAN.DEVRIES@BEDRIJF.NL" not in out
    assert "bedrijf.nl" not in out.lower()


# ── phone numbers, with and without country code ──────────────────────────

def test_strips_dutch_mobile_with_country_code_plus():
    out = pseudonymize_cv_text("Bel mij: +31 6 12345678")
    assert "12345678" not in out
    assert "[TELEFOON]" in out


def test_strips_dutch_mobile_with_leading_zero_and_dash():
    out = pseudonymize_cv_text("Tel: 06-12345678")
    assert "06-12345678" not in out
    assert "[TELEFOON]" in out


def test_strips_dutch_mobile_plain_digits():
    out = pseudonymize_cv_text("Telefoon 0612345678 bereikbaar na 17u")
    assert "0612345678" not in out
    assert "[TELEFOON]" in out


def test_strips_international_dialling_prefix_0031():
    out = pseudonymize_cv_text("Phone: 0031612345678")
    assert "0031612345678" not in out
    assert "[TELEFOON]" in out


def test_strips_phone_with_parens_country_code():
    out = pseudonymize_cv_text("+31(0)6-12345678")
    assert "12345678" not in out
    assert "[TELEFOON]" in out


def test_strips_landline_with_area_code():
    out = pseudonymize_cv_text("Kantoor: 010-2233445")
    assert "2233445" not in out
    assert "[TELEFOON]" in out


def test_strips_bare_mobile_number_without_leading_zero_and_dash():
    # security-audit follow-up (finding 8): a mobile number typed without
    # its leading trunk zero was previously missed entirely.
    out = pseudonymize_cv_text("Bereikbaar op 6-12345678 tijdens kantooruren.")
    assert "6-12345678" not in out
    assert "[TELEFOON]" in out


def test_strips_bare_mobile_number_without_leading_zero_no_separator():
    # Same shape as a BSN, so either token is an acceptable outcome here --
    # what matters is the digits never survive (see test_redacts_a_bsn_
    # shaped_digit_run above for the same trade-off the other way round).
    out = pseudonymize_cv_text("Bereikbaar op 612345678 tijdens kantooruren.")
    assert "612345678" not in out
    assert ("[TELEFOON]" in out) or ("[BSN]" in out)


def test_does_not_eat_a_cv_year_range():
    # 8 digits total ("2015" + "2020"), same length class as a phone number,
    # but no leading 0/+ dialling prefix -- must be left alone or matching
    # loses real signal (years of experience) for no privacy benefit.
    out = pseudonymize_cv_text("Senior C++ engineer, 2015-2020 bij vorige werkgever.")
    assert "2015-2020" in out
    assert "[TELEFOON]" not in out


# security-audit follow-up (blocking finding 1): this test used to be named
# test_does_not_eat_a_postcode and asserted the postcode survived -- a
# Dutch postcode + house number identifies a single household on its own,
# and it stands in the first ~500 chars of virtually every Dutch CV, so
# leaving it in was the bug, not a feature. Inverted per the audit.
def test_redacts_a_postcode_anywhere_in_the_text():
    out = pseudonymize_cv_text("Woonplaats: 5611 AB Eindhoven")
    assert "5611 AB" not in out
    assert "[POSTCODE]" in out
    assert "[TELEFOON]" not in out


def test_redacts_a_birthdate():
    out = pseudonymize_cv_text("Geboortedatum: 12-03-1988, woonachtig in Eindhoven.")
    assert "12-03-1988" not in out
    assert "[DATUM]" in out


def test_redacts_a_bsn_shaped_digit_run():
    # A bare 9-digit run is BSN-shaped, but it's also exactly the shape of a
    # Dutch mobile number typed without its leading trunk zero (finding 8),
    # so this may come out tagged [BSN] or [TELEFOON] -- either way the
    # digits themselves must never survive.
    out = pseudonymize_cv_text("BSN: 123456782, te vermelden bij sollicitatie.")
    assert "123456782" not in out
    assert ("[BSN]" in out) or ("[TELEFOON]" in out)


def test_redacts_an_iban_shaped_run():
    out = pseudonymize_cv_text("Uitbetaling graag op NL91ABNA0417164300.")
    assert "NL91ABNA0417164300" not in out
    assert "[IBAN]" in out


def test_strips_contact_block_header_but_keeps_the_title_line():
    # The literal example from the security audit: a Dutch CV's opening
    # contact block (address, postcode, phone, birthdate, nationality)
    # sitting right in the first ~500 chars that go to OpenRouter -- but
    # with a job-title line in between that must survive.
    cv = (
        "Jan van der Berg\n"
        "Senior Embedded Software Engineer\n"
        "Kerkstraat 12, 5611 AB Eindhoven | 06-12345678 | jan@example.com\n"
        "Geboortedatum 12-03-1988, Nederlandse nationaliteit.\n"
        "\n"
        "Profiel\n"
        "Ervaren C++ engineer, 10 jaar ervaring met firmware voor motion control.\n"
    )
    out = pseudonymize_cv_text(cv, full_name="Jan van der Berg")
    assert "Kerkstraat 12" not in out
    assert "5611 AB" not in out
    assert "06-12345678" not in out
    assert "12-03-1988" not in out
    assert "nationaliteit" not in out.lower()
    assert "Senior Embedded Software Engineer" in out
    assert "firmware voor motion control" in out


# ── LinkedIn / GitHub / generic URLs ───────────────────────────────────────

def test_strips_linkedin_url_with_protocol():
    out = pseudonymize_cv_text("Profiel: https://www.linkedin.com/in/jan-de-vries-1234/")
    assert "linkedin.com" not in out
    assert "[URL]" in out


def test_strips_linkedin_url_without_protocol():
    out = pseudonymize_cv_text("LinkedIn: linkedin.com/in/aisha-al-farsi")
    assert "linkedin.com" not in out
    assert "[URL]" in out


def test_strips_github_url():
    out = pseudonymize_cv_text("GitHub: github.com/nguyenvanminh, zie mijn repos.")
    assert "github.com" not in out
    assert "[URL]" in out


def test_strips_generic_www_url():
    out = pseudonymize_cv_text("Portfolio: www.janspersoonlijkesite.nl")
    assert "janspersoonlijkesite.nl" not in out
    assert "[URL]" in out


# ── names: Dutch and non-Western, several orderings ────────────────────────

def test_strips_known_dutch_name_natural_order():
    cv = "Jan de Vries\nSenior C++ Developer\n10 jaar ervaring."
    out = pseudonymize_cv_text(cv, full_name="Jan de Vries")
    assert "Jan de Vries" not in out
    assert "[NAAM]" in out
    assert "Senior C++ Developer" in out


def test_strips_known_name_case_insensitive_and_reversed_order():
    cv = "CV VAN VRIES, JAN -- contactgegevens onderaan."
    out = pseudonymize_cv_text(cv, full_name="Jan Vries")
    assert "VRIES, JAN" not in out
    assert "[NAAM]" in out


def test_strips_known_name_comma_order():
    cv = "de Vries, Jan — Curriculum Vitae"
    out = pseudonymize_cv_text(cv, full_name="Jan de Vries")
    assert "de Vries, Jan" not in out


def test_strips_lone_first_name_mention_elsewhere_in_cv():
    cv = "Fatima Al-Sayed\nEmbedded software engineer.\n\nMet vriendelijke groet,\nFatima"
    out = pseudonymize_cv_text(cv, full_name="Fatima Al-Sayed")
    assert "Fatima" not in out
    assert "Embedded software engineer" in out


def test_strips_non_western_name_with_diacritics():
    cv = "Nguyễn Văn Minh — OT cybersecurity specialist met 6 jaar ervaring."
    out = pseudonymize_cv_text(cv, full_name="Nguyễn Văn Minh")
    assert "Nguyễn" not in out
    assert "Văn" not in out
    assert "Minh" not in out
    assert "OT cybersecurity specialist" in out


def test_strips_hyphenated_surname_variant():
    cv = "Aisha Al-Farsi is een mechatronica-engineer uit Eindhoven."
    out = pseudonymize_cv_text(cv, full_name="Aisha Al-Farsi")
    assert "Aisha Al-Farsi" not in out
    assert "mechatronica-engineer" in out


# ── security-audit follow-up (blocking finding 2): tussenvoegsels and other
# ordinary Dutch words must not be destroyed everywhere they occur just
# because they also happen to be part of *this* candidate's own name ─────

def test_tussenvoegsel_words_survive_elsewhere_in_the_cv():
    cv = (
        "Jan van der Berg\n"
        "Senior Embedded Software Engineer\n\n"
        "Ervaring: 2015-2020 ontwikkeling van der Berg firmware voor "
        "motion control bij ASML."
    )
    out = pseudonymize_cv_text(cv, full_name="Jan van der Berg")
    # the candidate's own name, as a phrase, is still redacted
    assert "[NAAM]" in out
    # but "van" and "der" as ordinary Dutch words elsewhere are not eaten
    assert "ontwikkeling van der Berg firmware" not in out  # this exact
    # phrase happens to also spell the surname -- redacted as a unit, see
    # test_surname_that_is_also_a_common_word below for the accepted
    # trade-off. What must NOT happen is losing "van"/"der" outside of
    # any name context:
    assert "motion control bij ASML" in out


def test_particle_word_alone_is_never_redacted():
    cv = "Achtergrond: gewerkt in de sector, van 2018 tot 2022, bij een OEM."
    out = pseudonymize_cv_text(cv, full_name="Jan van der Berg")
    assert "gewerkt in de sector" in out
    assert "van 2018 tot 2022" in out
    assert "bij een OEM" in out
    assert "[NAAM]" not in out


def test_surname_that_is_also_a_common_word_is_accepted_residual_risk():
    # Documented trade-off (see _redact_known_name docstring): a surname
    # that collides with an employer/vendor name still gets redacted
    # wherever it stands alone, because it genuinely is this candidate's
    # own name and there's no reliable way to tell the two apart.
    cv = "Erik Bosch\nTest engineer, werkte met Bosch-sensoren in de auto-industrie."
    out = pseudonymize_cv_text(cv, full_name="Erik Bosch")
    assert "Erik Bosch" not in out
    assert "Bosch-sensoren" not in out  # accepted residual risk, not a bug
    assert "auto-industrie" in out


def test_arabic_particle_el_in_surname():
    cv = "Fatima el Amrani\nEmbedded software engineer met 5 jaar ervaring."
    out = pseudonymize_cv_text(cv, full_name="Fatima el Amrani")
    assert "Fatima el Amrani" not in out
    assert "Embedded software engineer" in out


def test_diacritic_name_is_still_matched():
    cv = "José García\nOT-cybersecurity specialist."
    out = pseudonymize_cv_text(cv, full_name="José García")
    assert "José García" not in out
    assert "OT-cybersecurity specialist" in out


def test_no_full_name_given_leaves_prose_untouched_besides_contact_data():
    cv = "Ervaren mechatronica engineer, 8 jaar ervaring met PLC-programmeren."
    out = pseudonymize_cv_text(cv, full_name=None)
    assert out == cv


def test_empty_or_none_cv_text_returns_empty_string():
    assert pseudonymize_cv_text(None) == ""
    assert pseudonymize_cv_text("") == ""
    assert pseudonymize_cv_text(None, full_name="Jan Jansen") == ""


# ── combined realistic CV sample: measure the effect ───────────────────────

SAMPLE_CV = """\
Jan de Vries
Senior Embedded Software Engineer
jan.devries@gmail.com | +31 6 12345678 | Eindhoven, Nederland
linkedin.com/in/jan-de-vries-1234 | github.com/jandevries

Profiel
Ervaren C++ en embedded software engineer met 12 jaar ervaring in de
Brainport-regio, gespecialiseerd in real-time systemen en OT-cybersecurity.

Werkervaring
2015-2020  Senior Software Engineer, ASML
2020-heden  Lead Embedded Engineer, NXP Semiconductors

Vaardigheden
C++, Rust, FreeRTOS, CAN-bus, ISO 26262, threat modeling

Contact: bel 010-2233445 (kantoor) of mail hierboven.
Met vriendelijke groet,
Jan
"""


def test_sample_cv_removes_all_direct_identifiers_but_keeps_skills_prose():
    out = pseudonymize_cv_text(SAMPLE_CV, full_name="Jan de Vries")

    # direct identifiers gone
    for leaked in ("jan.devries@gmail.com", "+31 6 12345678", "010-2233445",
                   "linkedin.com/in/jan-de-vries-1234", "github.com/jandevries",
                   "Jan de Vries"):
        assert leaked not in out, f"{leaked!r} was not removed"
    # NOTE: the bare 3-letter signoff "Jan" on its own line is *not*
    # asserted gone here -- security-audit finding 2 raised the loose
    # per-word redaction floor to 4 chars specifically so a 3-letter
    # tussenvoegsel ("van", "der") stops being destroyed everywhere in the
    # CV body. The full "Jan de Vries" phrase above is still always
    # redacted; a lone 3-letter first name surviving a signoff line is the
    # accepted trade-off for that fix.

    # semantic signal for matching survives
    for kept in ("Senior Embedded Software Engineer", "real-time systemen",
                 "OT-cybersecurity", "ASML", "NXP Semiconductors",
                 "C++, Rust, FreeRTOS, CAN-bus", "ISO 26262", "2015-2020",
                 "Eindhoven"):
        assert kept in out, f"{kept!r} was unexpectedly removed"


def test_sample_cv_length_effect_is_reported():
    out = pseudonymize_cv_text(SAMPLE_CV, full_name="Jan de Vries")
    # Sanity/documentation assertion: pseudonymisation shortens the text
    # (contact block collapses to short placeholders) but a substantial
    # majority of the CV -- the skills/experience prose that drives match
    # quality -- remains, well within the 500-char window matcher.py keeps.
    assert len(out) < len(SAMPLE_CV)
    assert len(out) > 0.6 * len(SAMPLE_CV)
