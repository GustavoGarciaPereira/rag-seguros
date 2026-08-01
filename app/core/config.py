from typing import FrozenSet, List

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.entities.insurance import DocumentType, Seguradora


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    admin_api_key: str = ""
    log_level: str = "INFO"
    enable_upload: str = "true"
    # Origens CORS permitidas (separadas por vírgula; "*" = qualquer origem)
    cors_origins: str = "*"
    # Rate limit por IP para endpoints de custo (ex.: /ask)
    rate_limit_per_minute: int = 30
    # True quando o serviço roda atrás de um proxy confiável que injeta
    # X-Forwarded-For (Render, nginx). Em dev/direto, mantenha False para
    # o rate limit não ser contornável com header forjado.
    trust_proxy_headers: bool = True
    # Dias de retenção do histórico de chat (purge automático na escrita)
    chat_retention_days: int = 30

    @property
    def upload_enabled(self) -> bool:
        return self.enable_upload.lower() != "false"


settings = Settings()

MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB
TEMP_DIR: str = "temp_uploads"

# Derivados dos enums de domínio — fonte única de verdade
ALLOWED_SEGURADORAS: List[str] = Seguradora.allowed_for_admin()
ALLOWED_DOCUMENT_TYPES: FrozenSet[str] = frozenset(t.value for t in DocumentType)
