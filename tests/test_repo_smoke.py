from pathlib import Path


def test_readme_is_french_and_human():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "Plateforme AIOps" in readme
    assert "déploiement" in readme.lower()


def test_cd_workflow_exists():
    assert Path(".github/workflows/cd.yml").exists()


def test_ci_workflow_mentions_tests_and_rollout_checks():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pytest -q" in ci
    assert "bandit" in ci
    assert "pip-audit" in ci
