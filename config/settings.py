from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    alpaca_api_key: str
    alpaca_secret_key: str

    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_temperature: float = 0.2

    fred_api_key: str = ""

    telegram_bot_token: str
    telegram_chat_id: str

    etf_symbols: str = "USO,BITO,SPY,QQQ,IWM,GLD"

    timezone: str = "America/New_York"
    log_level: str = "INFO"

    @field_validator("anthropic_temperature")
    @classmethod
    def clamp_temperature(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    def etf_symbols_list(self) -> list[str]:
        return [s.strip() for s in self.etf_symbols.split(",") if s.strip()]


settings = Settings()
