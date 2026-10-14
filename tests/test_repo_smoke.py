from pathlib import Path


def test_readme_describes_the_project_in_english():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "AIOps / MLOps Platform" in readme
    assert "Kubernetes" in readme
    assert "retraining" in readme.lower()


def test_cd_workflow_exists():
    assert Path(".github/workflows/cd.yml").exists()


def test_ci_workflow_mentions_tests_and_rollout_checks():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pytest -q" in ci
    assert "bandit" in ci
    assert "pip-audit" in ci
