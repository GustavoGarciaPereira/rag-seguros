from typing import FrozenSet, List

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.entities.insurance import DocumentType, Seguradora


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

# Derivados dos enums de domínio — fonte única de verdade
ALLOWED_SEGURADORAS: List[str] = Seguradora.allowed_for_admin()
ALLOWED_DOCUMENT_TYPES: FrozenSet[str] = frozenset(t.value for t in DocumentType)
