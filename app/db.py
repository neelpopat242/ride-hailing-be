from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

engine = None
SessionLocal = None


class Base(DeclarativeBase):
    pass


def init_db(app):
    global engine, SessionLocal
    engine = create_engine(app.config["DATABASE_URL"], pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    import app.models.user    # noqa: F401
    import app.models.driver  # noqa: F401
    import app.models.ride  # noqa: F401
    import app.models.ride_candidate  # noqa: F401
    import app.models.trip  # noqa: F401
    import app.models.payment  # noqa: F401

    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
