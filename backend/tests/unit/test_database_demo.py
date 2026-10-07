from sqlalchemy import inspect, select

from app.database import Database
from app.demo import load_demo_fixture
from app.models.base import SchemaMetadata


def test_database_initialization_is_idempotent_and_business_free(tmp_path):
    location = tmp_path / "nested" / "foundation.db"
    db = Database(f"sqlite:///{location}")
    db.initialize()
    db.initialize()
    assert location.exists() and db.healthy()
    assert set(inspect(db.engine).get_table_names()) == {
        "schema_metadata",
        "tracked_assets",
        "issuers",
        "token_metadata",
        "token_observations",
        "equity_observations",
        "news_events",
        "market_status",
        "ingestion_checkpoints",
        "exposure_proposals",
        "trust_assessments",
        "trust_samples",
        "trust_episodes",
    }
    with db.sessions() as session:
        rows = session.scalars(select(SchemaMetadata)).all()
        assert [(row.key, row.value) for row in rows] == [("schema_version", "4")]
    db.close()
    reopened = Database(f"sqlite:///{location}")
    reopened.initialize()
    assert reopened.healthy()
    reopened.close()


def test_sqlite_memory_connection_is_shared():
    db = Database("sqlite:///:memory:")
    db.initialize()
    with db.sessions() as session:
        assert session.get(SchemaMetadata, "schema_version").value == "4"
    db.close()


def test_demo_fixture_is_deterministic_isolated_and_non_executable():
    first, second = load_demo_fixture(), load_demo_fixture()
    assert first.model_dump_json() == second.model_dump_json()
    assert first.data_mode == "DEMO" and first.execution_allowed is False
    assert first.phase == 1
    assert set(type(first).model_fields) == {
        "fixture_id",
        "data_mode",
        "execution_allowed",
        "service_name",
        "phase",
        "observed_at",
    }


def test_proposal_table_upgrade_preserves_prior_data(tmp_path):
    from sqlalchemy import text

    db = Database(f"sqlite:///{tmp_path}/upgrade.db")
    db.initialize()
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE schema_metadata SET value='2' WHERE key='schema_version'"))
        connection.execute(
            text("INSERT INTO schema_metadata(key,value) VALUES('historical-evidence','preserved')")
        )
        connection.execute(text("DROP TABLE exposure_proposals"))
    db.initialize()
    with db.sessions() as session:
        assert session.get(SchemaMetadata, "historical-evidence").value == "preserved"
        assert session.get(SchemaMetadata, "schema_version").value == "4"
    assert "exposure_proposals" in inspect(db.engine).get_table_names()
    db.close()
