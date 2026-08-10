from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aomarket:aomarket@localhost:55432/aomarket"

    # DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME are an alternate way to
    # configure the database connection, for operators (e.g. Zalando's
    # postgres-operator) that hand out per-role username/password Secrets
    # rather than a single connection-string secret. Leave DB_HOST blank
    # (the default) to configure via DATABASE_URL instead.
    db_host: str = ""
    db_port: int = 5432
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""

    @model_validator(mode="after")
    def _compose_database_url_from_parts(self) -> "AppConfig":
        if self.db_host:
            # quote(safe="") -- a username/password from a generated Secret could
            # contain characters (@, :, /) that would otherwise be misparsed as
            # URL structure.
            user = quote(self.db_user, safe="")
            password = quote(self.db_password, safe="")
            self.database_url = (
                f"postgresql+asyncpg://{user}:{password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self

    ao_login: str = ""
    ao_password: str = ""
    ao_character: str = ""
    ao_chat_server: str = "chat.d1.funcom.com"
    ao_chat_port: int = 7105

    # Player always treated as admin for API key purposes, regardless of
    # MarketUser.is_admin -- bootstraps the first admin. Leave blank to
    # disable owner-bootstrap admin (MarketUser.is_admin is then the only
    # path to admin). Chat-issued keys are scoped to whatever identity the
    # bot resolved for that player (their name once AOCP_CLIENT_NAME has
    # arrived, otherwise their numeric character id) -- set this to match
    # whichever one applies for your account if owner-bootstrap isn't
    # taking effect.
    ao_owner_character: str = ""

    # Server-side secret mixed into API key hashing (PBKDF2-HMAC-SHA256) --
    # an attacker who steals only the database still can't brute-force
    # tokens without this too. Leave blank to hash without a pepper (still
    # PBKDF2-hardened, just without that extra layer). Changing this
    # invalidates every previously-issued key.
    api_key_pepper: str = ""

    aodb_api_url: str = "https://aodb-api.ao.yeetbox.net"
    gmi_api_url: str = "https://gmi.nadybot.org"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    log_level: str = "INFO"


def load_config() -> AppConfig:
    return AppConfig()
