import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.story_plan import project_state_repository
from app.models import ProjectWorkspace  # noqa: F401


@pytest.fixture
def project_state_store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    project_state_repository.bind_session_factory(session_factory)
    try:
        yield session_factory
    finally:
        project_state_repository.restore_default_session_factory()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
