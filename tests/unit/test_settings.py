from src.config.settings import Settings


def test_database_url_postgres_scheme_is_normalized() -> None:
    settings = Settings(database_url="postgres://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_database_url_postgresql_scheme_is_normalized() -> None:
    settings = Settings(database_url="postgresql://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_database_url_with_driver_is_untouched() -> None:
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert Settings(database_url=url).database_url == url


def test_sqlite_url_is_untouched() -> None:
    assert Settings(database_url="sqlite://").database_url == "sqlite://"


def test_cors_origins_list_splits_and_strips() -> None:
    settings = Settings(cors_origins="http://a.com, https://b.com ,")
    assert settings.cors_origins_list == ["http://a.com", "https://b.com"]
