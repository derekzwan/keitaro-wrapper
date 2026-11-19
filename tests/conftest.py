import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base, get_db, make_engine
from app.keitaro import KeitaroClient, set_keitaro
from app.main import app
from tests import fake_keitaro


@pytest.fixture
def fake():
    fake_keitaro.state = fake_keitaro.State()
    # роуты читают модульную переменную state — подменяем её во всех обработчиках
    yield fake_keitaro.state


@pytest.fixture
def settings():
    return Settings(keitaro_url="http://kt", keitaro_api_key=fake_keitaro.API_KEY, _env_file=None)


@pytest.fixture
def kt(fake, settings):
    http = TestClient(
        fake_keitaro.app,
        base_url="http://kt/admin_api/v1",
        headers={"Api-Key": fake_keitaro.API_KEY},
    )
    client = KeitaroClient(settings, http=http)
    set_keitaro(client)
    yield client
    set_keitaro(None)


@pytest.fixture
def db_session_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture
def api(kt, db_session_factory, settings):
    from app.config import get_settings

    def _db():
        s = db_session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
