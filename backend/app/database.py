from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import data_tables  # noqa: F401 — register the Phase 2 ORM tables
from app.models.base import Base, SchemaMetadata


class Database:
    def __init__(self, url: str):
        database = make_url(url).database
        if database != ":memory:":
            Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 5},
            poolclass=StaticPool if database == ":memory:" else None,
        )
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            statement = insert(SchemaMetadata).values(key="schema_version", value="4")
            connection.execute(
                statement.on_conflict_do_update(index_elements=["key"], set_={"value": "4"})
            )
        if not self.healthy():
            raise RuntimeError("Database initialization failed")

    def healthy(self) -> bool:
        try:
            with self.engine.connect() as connection:
                return connection.execute(text("SELECT 1")).scalar_one() == 1
        except Exception:
            return False

    def close(self) -> None:
        self.engine.dispose()
