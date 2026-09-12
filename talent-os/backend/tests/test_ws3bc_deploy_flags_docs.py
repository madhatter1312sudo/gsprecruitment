"""
WS3b/WS3c, laatste reparatieronde: de drie reparaties die niet in de
Python-code zelf zitten maar wel kunnen verlopen zonder dat iemand het
merkt.

  1. De volgorde in .github/workflows/deploy.yml (bouwen, migreren, dan
     pas omschakelen). Draait die ooit weer om, dan geeft elke login
     tijdens een deploy met een migratie een 500.
  2. De tweede rem op de vacature-alerts: migratie 042 moet de rij
     `system_settings.job_alerts_enabled` op 'false' aanmaken, anders
     beschrijven docs/VERWERKINGSREGISTER.md en core/config.py een
     schakelaar die niet bestaat (`_flag_enabled()` geeft True terug bij
     een ontbrekende sleutel).
  3. De eigenaarschecklist in docs/EMAIL-SETUP.md §9, met de volgorde die
     ertoe doet: de WAF-uitzondering vóór het aanzetten van de alerts.

Geen DB en geen netwerk: dit leest bestanden.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEPLOY_YML = os.path.join(REPO_ROOT, ".github", "workflows", "deploy.yml")
EMAIL_SETUP = os.path.join(REPO_ROOT, "docs", "EMAIL-SETUP.md")
MIGRATION_042 = os.path.join(
    REPO_ROOT, "talent-os", "backend", "migrations", "042_alerts_token_binding_dormant_skip.py",
)
MATCHING_PY = os.path.join(REPO_ROOT, "talent-os", "backend", "core", "matching.py")


def _deploy_steps():
    with open(DEPLOY_YML, encoding="utf-8") as f:
        workflow = yaml.safe_load(f)
    return workflow["jobs"]["deploy"]["steps"]


def _step_index(predicate) -> int:
    for i, step in enumerate(_deploy_steps()):
        if predicate(step.get("run") or ""):
            return i
    return -1


def test_deploy_yml_is_valid_yaml_with_a_deploy_job():
    steps = _deploy_steps()
    assert steps
    assert any((s.get("name") or "") == "Run database migrations" for s in steps)


def test_migrations_run_before_the_new_backend_goes_live():
    """Het venster waarin nieuwe code op het oude schema draait. Concreet:
    core/retention.py's LOGIN_STAMP_SQL schrijft kolommen uit migratie 042
    in alle vier de inlogpaden, zonder try/except."""
    build = _step_index(lambda run: "docker compose build backend" in run)
    migrate = _step_index(lambda run: "migrations/0*.py" in run)
    start = _step_index(lambda run: re.search(r"docker compose up -d(?: --wait)? backend", run) is not None)

    assert build >= 0, "geen aparte buildstap meer"
    assert migrate >= 0, "geen migratiestap meer"
    assert start >= 0, "geen stap die de backend start"
    assert build < migrate < start, "bouwen, migreren, dan pas omschakelen"


def test_no_deploy_step_builds_and_starts_the_backend_in_one_go():
    """`docker compose up -d --build backend` is precies de vorm die het
    venster terugbrengt: hij zet de nieuwe code live vóór de migraties."""
    for step in _deploy_steps():
        run = step.get("run") or ""
        assert "up -d --build backend" not in run


def test_the_migration_step_still_uses_a_one_off_container_on_the_new_image():
    """Wat de migratiestap doet is niet veranderd, alleen waar hij staat."""
    steps = _deploy_steps()
    migrate = next(s for s in steps if (s.get("name") or "") == "Run database migrations")
    run = migrate["run"]
    assert "docker compose run --rm -T --no-deps backend" in run
    assert "for f in migrations/0*.py" in run


def test_postgres_is_started_explicitly_now_that_the_backend_step_no_longer_does_it():
    """De migratiestap gebruikt --no-deps en kreeg postgres tot nu toe
    stilzwijgend van de `up -d --build backend` die ervoor stond."""
    build = _step_index(lambda run: "docker compose build backend" in run)
    assert build >= 0
    assert "up -d --wait postgres" in (_deploy_steps()[build].get("run") or "")


def test_the_rollback_branch_still_exists_and_runs_only_on_failure():
    rollback = next(
        s for s in _deploy_steps() if (s.get("name") or "").startswith("Roll back to previous image")
    )
    assert rollback.get("if") == "failure()"
    assert "gsp-recruitment-backend:previous" in rollback["run"]


# ── Migratie 042: de tweede rem ──────────────────────────────────────────

def test_migration_042_creates_the_job_alerts_flag_row_idempotently():
    with open(MIGRATION_042, encoding="utf-8") as f:
        source = f.read()
    assert "INSERT INTO system_settings" in source
    assert "'job_alerts_enabled', 'false'" in source
    # ON CONFLICT: nooit een waarde terugzetten die de eigenaar zelf op
    # 'true' heeft gezet, ook niet bij een herhaalde deploy.
    assert "ON CONFLICT (key) DO NOTHING" in source


def test_the_flag_default_is_dry_run_not_enabled():
    with open(MIGRATION_042, encoding="utf-8") as f:
        source = f.read()
    assert "'job_alerts_enabled', 'true'" not in source


# ── docs/EMAIL-SETUP.md §9: de eigenaarschecklist ────────────────────────

def _checklist_section() -> str:
    with open(EMAIL_SETUP, encoding="utf-8") as f:
        text = f.read()
    start = text.index("## 9. Eigenaarschecklist na de merge")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_email_setup_has_the_owner_checklist_as_section_9():
    section = _checklist_section()
    for number in range(1, 7):
        assert f"\n{number}. " in section, f"stap {number} ontbreekt"


def test_the_waf_exception_comes_before_switching_the_alerts_on():
    """Anders belooft de privacyverklaring een afmeldknop die niets doet."""
    section = _checklist_section()
    waf = section.index("/api/public/unsubscribe")
    alerts_on = section.index("JOB_ALERTS_ENABLED=true")
    assert waf < alerts_on


def test_the_checklist_says_the_db_flag_step_is_handled_by_the_migration():
    section = _checklist_section()
    assert "Vervalt" in section
    assert "042" in section


def test_the_checklist_names_the_dry_run_log_line_to_read():
    section = _checklist_section()
    assert "dormant_account_warning_job: accounts_due=" in section


# ── Huisregel: geen gedachtestreepjes in eigen tekst ─────────────────────

def test_core_matching_has_no_em_dash():
    with open(MATCHING_PY, encoding="utf-8") as f:
        assert "—" not in f.read()

