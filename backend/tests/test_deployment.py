"""Deployment-focused tests.

Covers the pieces added/verified for secure cloud deployment without needing
a real Postgres instance: settings resolution (Render ``DATABASE_URL`` alias,
driver normalisation), the optional bearer-token auth gate, the public
bootstrap endpoint, SPA serving from the API, the SQLite->Postgres importer
(logic exercised against throwaway SQLite databases), and the schema dispatch.

PG-only behaviour (``ensure_postgres``, sequence re-arming) is verified with
mocks; the user runs the importer against the real managed Postgres once,
guided by DEPLOYMENT.md.
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings

# --------------------------------------------------------------------------- #
# Settings resolution
# --------------------------------------------------------------------------- #


class TestSettingsResolution:
    def test_bare_database_url_falls_back(self, monkeypatch):
        monkeypatch.delenv("PILOTE_DATABASE_URL", raising=False)
        monkeypatch.setenv(
            "DATABASE_URL", "postgres://user:pw@host:5432/db?sslmode=require"
        )
        settings = Settings(_env_file=None)
        assert settings.resolved_database_url == (
            "postgresql+psycopg://user:pw@host:5432/db?sslmode=require"
        )

    def test_bare_database_url_ignored_when_pilote_set(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@host:5432/wrong")
        monkeypatch.setenv("PILOTE_DATABASE_URL", "postgresql://user:pw@host:5432/right")
        settings = Settings(_env_file=None)
        assert settings.resolved_database_url == (
            "postgresql+psycopg://user:pw@host:5432/right"
        )

    def test_postgresql_urls_normalised(self, monkeypatch):
        monkeypatch.delenv("PILOTE_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for url in ("postgres://u:p@h/db", "postgresql://u:p@h/db"):
            settings = Settings(_env_file=None, database_url=url)
            assert settings.resolved_database_url.startswith("postgresql+psycopg://")

    def test_sqlite_relative_path_becomes_absolute(self):
        settings = Settings(_env_file=None, database_url="sqlite:///./data/t.db")
        url = settings.resolved_database_url
        assert url.startswith("sqlite:///")
        assert "backend" in url

    def test_wildcard_cors_rejected(self, monkeypatch):
        monkeypatch.setenv("PILOTE_CORS_ORIGINS", '["*"]')
        with pytest.raises(Exception):
            Settings(_env_file=None)

    def test_auth_flags(self):
        assert Settings(_env_file=None, access_token=None).auth_enabled is False
        assert Settings(_env_file=None, access_token="").auth_enabled is False
        assert Settings(_env_file=None, access_token="sekret").auth_enabled is True


# --------------------------------------------------------------------------- #
# Engine configuration
# --------------------------------------------------------------------------- #


class TestEngineConfig:
    def test_postgres_engine_gets_ping_and_recycle(self, monkeypatch):
        from app.db.session import _build_engine

        monkeypatch.delenv("PILOTE_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:p@h/db")
        engine = _build_engine(settings)
        assert engine.pool._pre_ping is True
        assert engine.pool._recycle == 1800

    def test_sqlite_engine_keeps_threaded_connect_args(self):
        from app.db.session import _build_engine

        settings = Settings(_env_file=None, database_url="sqlite:///:memory:")
        engine = _build_engine(settings)
        assert engine.pool._pre_ping is False
        assert engine.pool._recycle == -1


# --------------------------------------------------------------------------- #
# Auth gate + bootstrap endpoint
# --------------------------------------------------------------------------- #


def _auth_app(settings: Settings, *, token: str | None):
    from app.main import create_app

    cfg = Settings(
        database_url=settings.database_url,
        environment="test",
        auto_migrate=True,
        access_token=token,
    )
    return create_app(cfg)


class TestAuthGate:
    def test_protected_routes_require_token(self, settings):
        app = _auth_app(settings, token="yes-secret")
        with TestClient(app) as client:
            assert client.get("/api/v1/health").status_code == 200
            cfg = client.get("/api/v1/config")
            assert cfg.status_code == 200
            assert cfg.json()["auth_required"] is True

            guarded = client.get("/api/v1/profile")
            assert guarded.status_code == 401
            assert client.get(
                "/api/v1/profile", headers={"Authorization": "Bearer wrong"}
            ).status_code == 401
            assert client.get(
                "/api/v1/profile", headers={"Authorization": "Bearer yes-secret"}
            ).status_code == 200

    def test_missing_token_allows_everything(self, settings):
        app = _auth_app(settings, token=None)
        with TestClient(app) as client:
            assert client.get("/api/v1/profile").status_code == 200
            assert client.get("/api/v1/config").json()["auth_required"] is False

    def test_config_never_exposes_token(self, settings):
        app = _auth_app(settings, token="super-secret")
        with TestClient(app) as client:
            body = client.get("/api/v1/config").json()
            assert "super-secret" not in str(body)


# --------------------------------------------------------------------------- #
# SPA serving
# --------------------------------------------------------------------------- #


class TestSpaServing:
    def _spa_app(self, settings, dist, *, serve=True):
        from app.main import create_app

        cfg = Settings(
            database_url=settings.database_url,
            environment="test",
            auto_migrate=True,
            serve_frontend=serve,
            frontend_dist=dist,
        )
        return create_app(cfg)

    def test_serves_index_and_assets_with_api_priority(self, settings, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "assets").mkdir()
        (dist / "index.html").write_text("<html><body>pilote-spa</body></html>")
        (dist / "assets" / "app.js").write_text("console.log('pilote');")

        app = self._spa_app(settings, dist)
        with TestClient(app) as client:
            root = client.get("/")
            assert root.status_code == 200
            assert "pilote-spa" in root.text
            assert "text/html" in root.headers["content-type"]

            deep_route = client.get("/settings/months")
            assert deep_route.status_code == 200
            assert "pilote-spa" in deep_route.text

            asset = client.get("/assets/app.js")
            assert asset.status_code == 200
            assert "pilote" in asset.text

            health = client.get("/api/v1/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            unknown_api = client.get("/api/not-real")
            assert unknown_api.status_code == 404
            assert unknown_api.json() == {"detail": "Not found"}

    def test_json_root_when_not_serving_frontend(self, settings, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>x</html>")
        app = self._spa_app(settings, dist, serve=False)
        with TestClient(app) as client:
            assert client.get("/").json()["api"] == "/api/v1"


# --------------------------------------------------------------------------- #
# Schema dispatch
# --------------------------------------------------------------------------- #


class TestSchemaDispatch:
    def test_postgres_schema_routes_to_ensure_postgres(self, monkeypatch):
        from app.db import schema as schema_mod

        calls: list[str] = []
        monkeypatch.setattr(schema_mod, "ensure_postgres", lambda settings: calls.append("postgres"))
        monkeypatch.setattr(schema_mod, "run_migrations", lambda url: calls.append("alembic"))

        settings = Settings(
            _env_file=None, database_url="postgresql+psycopg://u:p@h/db", auto_migrate=True
        )
        schema_mod.ensure_schema(settings)
        assert calls == ["postgres"]

    def test_sqlite_schema_routes_to_alembic(self, monkeypatch):
        from app.db import schema as schema_mod

        calls: list[str] = []
        monkeypatch.setattr(schema_mod, "ensure_postgres", lambda settings: calls.append("postgres"))
        monkeypatch.setattr(schema_mod, "run_migrations", lambda url: calls.append("alembic"))

        settings = Settings(_env_file=None, database_url="sqlite:///:memory:", auto_migrate=True)
        schema_mod.ensure_schema(settings)
        assert calls == ["alembic"]

    def test_auto_migrate_false_does_nothing(self, monkeypatch):
        from app.db import schema as schema_mod

        calls: dict = {"n": 0}
        monkeypatch.setattr(schema_mod, "ensure_postgres", lambda s: calls.__setitem__("n", calls["n"] + 1))
        settings = Settings(
            _env_file=None, database_url="postgresql+psycopg://u:p@h/db", auto_migrate=False
        )
        schema_mod.ensure_schema(settings)
        assert calls["n"] == 0


class TestEnsurePostgres:
    def test_creates_tables_and_stamps_when_version_missing(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.db import schema as schema_mod

        created = []
        stamped = []
        fake_inspect = MagicMock()
        fake_inspect().has_table.return_value = False

        connection = MagicMock()
        connection.execute.return_value.scalar.return_value = None
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        monkeypatch.setattr("app.db.session.get_engine", lambda: engine)
        monkeypatch.setattr(
            "app.db.base.Base.metadata.create_all", lambda eng: created.append(eng)
        )
        monkeypatch.setattr("sqlalchemy.inspect", lambda obj: fake_inspect(obj))
        monkeypatch.setattr(
            "alembic.command.stamp",
            lambda cfg, revision: stamped.append((cfg, revision)),
        )

        settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:p@h/db")
        schema_mod.ensure_postgres(settings)

        assert created == [engine]
        assert stamped and stamped[0][1] == "head"


# --------------------------------------------------------------------------- #
# SQLite -> Postgres importer (logic runs against throwaway SQLite)
# --------------------------------------------------------------------------- #

TABLE_NAMES = (
    "profiles",
    "categories",
    "accounts",
    "goals",
    "budgets",
    "recurring_transactions",
    "transactions",
    "transfers",
    "budget_allocations",
)


def _seed_source(url: str) -> dict:
    from app.db.base import Base
    from app import models  # noqa: F401  (register models)

    source = create_engine(url)
    Base.metadata.create_all(source)
    with source.begin() as conn:
        conn.execute(
            Base.metadata.tables["profiles"].insert().values(
                id=1,
                currency="EUR",
                month_start_day=1,
                timezone="Europe/Paris",
                preferences="{}",
            )
        )
        categories = Base.metadata.tables["categories"]
        accounts = Base.metadata.tables["accounts"]
        transactions = Base.metadata.tables["transactions"]
        parent_id = conn.execute(
            categories.insert().values(
                name="Transport", type="expense", parent_id=None
            )
        ).inserted_primary_key[0]
        child_id = conn.execute(
            categories.insert().values(
                name="Fuel", type="expense", parent_id=parent_id
            )
        ).inserted_primary_key[0]
        account_id = conn.execute(
            accounts.insert().values(
                name="Chequing",
                type="checking",
                currency="EUR",
                opening_balance=1000.0,
            )
        ).inserted_primary_key[0]
        conn.execute(
            transactions.insert().values(
                account_id=account_id,
                category_id=child_id,
                type="expense",
                amount=-50.0,
                date=datetime.date(2025, 6, 1),
                description="Shell",
            )
        )
    source.dispose()
    return {"parent_id": parent_id, "child_id": child_id, "account_id": account_id}


class TestImporterCore:
    def test_import_preserves_ids_and_relations(self, tmp_path):
        from app.tools.import_sqlite import import_sqlite

        source_url = f"sqlite:///{tmp_path}/source.db"
        target_url = f"sqlite:///{tmp_path}/target.db"
        ids = _seed_source(source_url)
        result = import_sqlite(source_url, target_url, force=False)

        assert result.table_counts["profiles"] == 1
        assert result.table_counts["categories"] == 2
        assert result.table_counts["accounts"] == 1
        assert result.table_counts["transactions"] == 1
        assert result.total == 5

        from app.db.base import Base

        target = create_engine(target_url)
        with target.connect() as conn:
            cats = conn.execute(text("SELECT id, parent_id FROM categories ORDER BY id")).all()
            assert [row[1] for row in cats] == [None, ids["parent_id"]]
            txn = conn.execute(text("SELECT account_id, category_id FROM transactions")).one()
            assert txn[0] == ids["account_id"]
            assert txn[1] == ids["child_id"]
            profile = conn.execute(text("SELECT currency, timezone FROM profiles")).one()
            assert profile[0] == "EUR" and profile[1] == "Europe/Paris"

    def test_refuses_non_empty_target(self, tmp_path):
        from app.tools.import_sqlite import import_sqlite

        source_url = f"sqlite:///{tmp_path}/source.db"
        target_url = f"sqlite:///{tmp_path}/target.db"
        _seed_source(source_url)
        _seed_source(target_url)

        with pytest.raises(SystemExit, match="already contains data"):
            import_sqlite(source_url, target_url, force=False)

    def test_refuses_same_database(self, tmp_path):
        from app.tools.import_sqlite import import_sqlite

        url = f"sqlite:///{tmp_path}/same.db"
        _seed_source(url)
        with pytest.raises(SystemExit, match="must be different"):
            import_sqlite(url, url, force=False)

    def test_refuses_missing_tables(self, tmp_path):
        from app.tools.import_sqlite import import_sqlite

        source_url = f"sqlite:///{tmp_path}/source.db"
        target_url = f"sqlite:///{tmp_path}/target.db"
        engine = create_engine(source_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE profiles (id INTEGER PRIMARY KEY)"))
        engine.dispose()

        with pytest.raises(SystemExit, match="missing tables"):
            import_sqlite(source_url, target_url, force=False)

    def test_refuses_non_sqlite_source(self):
        from app.tools.import_sqlite import import_sqlite

        with pytest.raises(SystemExit, match="must be a SQLite"):
            import_sqlite("postgresql://u:p@h/a", "postgresql+psycopg://u:p@h/b")


class TestImporterHelpers:
    def test_normalize_adds_psycopg_driver(self):
        from app.tools.import_sqlite import _normalize

        assert _normalize("postgres://u:p@h/db").startswith("postgresql+psycopg://")
        assert _normalize("postgresql://u:p@h/db").startswith("postgresql+psycopg://")
        assert _normalize("sqlite:///x.db") == "sqlite:///x.db"

    def test_masked_redacts_password(self):
        from app.tools.import_sqlite import _masked

        assert "hunter2" not in _masked("postgresql+psycopg://user:hunter2@host/db")
        assert "***" in _masked("postgresql+psycopg://user:hunter2@host/db")

    def test_category_order_parents_first(self):
        from app.tools.import_sqlite import _order_by_dependency

        rows = [
            {"id": 3, "parent_id": 1, "name": "Child"},
            {"id": 1, "parent_id": None, "name": "Root"},
            {"id": 4, "parent_id": 3, "name": "Grandchild"},
        ]
        ordered = _order_by_dependency(rows, "parent_id")
        assert ordered[0]["id"] == 1
        assert ordered[1]["id"] == 3
        assert ordered[2]["id"] == 4


class TestImporterCliDialectGuard:
    def test_cli_rejects_non_postgres_target(self, tmp_path, capsys):
        from app.tools.import_sqlite import _cli_main

        with pytest.raises(SystemExit):
            _cli_main(
                [
                    "--sqlite",
                    str(tmp_path / "source.db"),
                    "--target",
                    "mysql://u:p@h/db",
                    "--yes",
                ]
            )
        assert "PostgreSQL" in capsys.readouterr().err