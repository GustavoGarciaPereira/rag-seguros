from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import FrozenSet, List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    admin_api_key: str = ""
    log_level: str = "INFO"
    enable_upload: str = "true"

    @property
    def upload_enabled(self) -> bool:
        return self.enable_upload.lower() != "false"


settings = Settings()

MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB
TEMP_DIR: str = "temp_uploads"

ALLOWED_DOCUMENT_TYPES: FrozenSet[str] = frozenset(
    {"apolice", "sinistro", "cobertura", "franquia", "endosso"}
)

ALLOWED_SEGURADORAS: List[str] = [
    "Bradesco", "Porto Seguro", "Azul", "Allianz",
    "Tokio Marine", "Liberty", "Mapfre",
]
