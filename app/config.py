from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    keitaro_url: str = ""
    keitaro_api_key: str = ""
    keitaro_timeout: float = 20.0
    keitaro_timezone: str = "Europe/Moscow"

    # Значения по умолчанию для создаватора: ищутся по имени среди того, что отдаёт API.
    default_domain: str = ""
    default_group: str = ""
    default_source: str = ""
    google_url: str = "https://google.com"

    database_url: str = "sqlite:///./keitaro_wrapper.db"
    offers_cache_ttl: int = 60

    @property
    def keitaro_api_base(self) -> str:
        return self.keitaro_url.rstrip("/") + "/admin_api/v1"

    @property
    def keitaro_admin_base(self) -> str:
        return self.keitaro_url.rstrip("/") + "/admin/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
