from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mqtt_host: str = "mqtt"
    mqtt_port: int = 1883
    database_url: str = "postgresql+asyncpg://grideye:grideye@database:5432/grideye"
    service_timeout_seconds: float = 15.0
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
