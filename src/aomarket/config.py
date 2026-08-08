from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aomarket:aomarket@localhost:55432/aomarket"

    ao_login: str = ""
    ao_password: str = ""
    ao_character: str = ""
    ao_chat_server: str = "chat.d1.funcom.com"
    ao_chat_port: int = 7105

    aodb_api_url: str = "https://aodb-api.ao.yeetbox.net"
    gmi_api_url: str = "https://gmi.nadybot.org"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    log_level: str = "INFO"


def load_config() -> AppConfig:
    return AppConfig()
