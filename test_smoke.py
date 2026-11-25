"""
Smoke tests — verify that all modules import and basic components instantiate
correctly without requiring network access or credentials.
"""
import importlib
import sqlite3
import tempfile
import os


def test_config_imports():
    from config import Config
    cfg = Config()
    assert isinstance(cfg.DB_PATH, str)
    assert isinstance(cfg.ENABLE_SELF_TRAINING, bool)


def test_firms_imports():
    from firms import FIRMS, FIRMS_BY_ID
    assert len(FIRMS) > 0
    assert isinstance(FIRMS_BY_ID, dict)
    # Every firm with a careers_url has an id
    for f in FIRMS:
        assert "id" in f
        assert "name" in f


def test_all_scraper_modules_import():
    modules = [
        "scrapers.base",
        "scrapers.jobs",
        "scrapers.job_boards",
        "scrapers.recruiter",
        "scrapers.press",
        "scrapers.chambers",
        "scrapers.rss",
        "scrapers.website",
        "scrapers.google_news",
        "scrapers.law360_me",
        "scrapers.linkedin_people",
        "scrapers.regulatory_registry",
        "scrapers.legal_media",
        "scrapers.alsp",
    ]
    for mod in modules:
        importlib.import_module(mod)


def test_database_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from database.db import Database
        db = Database(db_path)
        # Check that the key tables were created
        conn = sqlite3.connect(db_path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        db.close()
        assert "signals" in tables
        assert "weekly_scores" in tables
    finally:
        os.unlink(db_path)


def test_expansion_analyzer_imports():
    from analysis.signals import ExpansionAnalyzer


def test_notifier_imports():
    from alerts.notifier import Notifier


def test_dashboard_generator_imports():
    from dashboard.generator import DashboardGenerator


def test_evolution_imports():
    from learning.evolution import load_weights, apply_learned_weights_to_signal
    weights = load_weights()
    assert isinstance(weights, dict)


def test_recruiter_cache_global_not_reassigned():
    """Regression: global _RECRUITER_CACHE should not appear in _populate_cache."""
    import ast
    import scrapers.recruiter as mod
    with open(mod.__file__) as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_populate_cache":
            for child in ast.walk(node):
                if isinstance(child, ast.Global) and "_RECRUITER_CACHE" in child.names:
                    raise AssertionError(
                        "Unnecessary 'global _RECRUITER_CACHE' found in _populate_cache"
                    )
