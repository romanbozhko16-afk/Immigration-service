"""Database engines. SQLite for the demo; any SQLAlchemy URL (e.g. Postgres) works."""

from sqlalchemy import Engine, create_engine, event


def make_engine(url: str) -> Engine:
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            # Overwrite deleted content on disk instead of leaving it in free pages.
            cursor.execute("PRAGMA secure_delete = ON")
            cursor.close()

    return engine
