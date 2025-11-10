"""
Google API standards compliant configuration management
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings with Google API compliance"""

    def __init__(self):
        # Application Metadata
        self.app_name: str = "Medical Report Parser API"
        self.app_version: str = "1.0.0"
        self.app_description: str = "REST API for parsing medical reports using Google Gemini"
        self.environment: str = os.getenv("ENVIRONMENT", "production")
        self.debug: bool = self.environment == "development"

        # Server Configuration
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8090"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

        # CORS Configuration
        self.cors_origins: list = self._parse_cors_origins(
            os.getenv("CORS_ORIGINS", "*")
        )

        # API Configuration
        self.api_version: str = "v1"
        self.api_prefix: str = f"/api/{self.api_version}"

        # Authentication
        self.require_auth: bool = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
        self.api_keys: list = self._parse_api_keys(os.getenv("API_KEYS", ""))
        self.require_tenant_header: bool = (
            os.getenv("REQUIRE_TENANT_HEADER", "false").lower() == "true"
        )
        self.admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
        self.rate_limit_requests_per_minute: int = int(
            os.getenv("RATE_LIMIT_PER_MINUTE", "120")
        )
        self.jwt_secret: str = os.getenv("JWT_SECRET", "")
        self.jwt_audience: Optional[str] = os.getenv("JWT_AUDIENCE")
        self.jwt_issuer: Optional[str] = os.getenv("JWT_ISSUER")

        # Gemini AI Configuration
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.max_tokens: int = int(os.getenv("MAX_TOKENS", "8192"))
        self.temperature: float = float(os.getenv("TEMPERATURE", "0.1"))

        # Azure Blob Storage Configuration
        self.azure_connection_string: str = os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING",
            "",
        )
        self.azure_container_name: str = os.getenv("AZURE_CONTAINER_NAME", "apilog")

        self.mongodb_url: str = os.getenv(
            "MONGODB_URL",
            "mongodb://localhost:27017"
        )
        self.mongodb_database: str = os.getenv(
            "MONGODB_DATABASE",
            "medical_report_parser"
        )

        # Timeout Configuration
        self.pdf_parse_timeout: int = int(os.getenv("PDF_PARSE_TIMEOUT", "300"))
        self.storage_timeout: int = int(os.getenv("STORAGE_TIMEOUT", "60"))

        # File Upload Configuration
        self.allowed_extensions: list = [".pdf"]
        self.max_file_size: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB default

    @staticmethod
    def _parse_cors_origins(origins_str: str) -> list:
        """Parse CORS origins from environment variable"""
        if origins_str == "*":
            return ["*"]
        return [origin.strip() for origin in origins_str.split(",")]

    @staticmethod
    def _parse_api_keys(keys_str: str) -> list:
        """Parse API keys from environment variable"""
        if not keys_str:
            return []
        return [key.strip() for key in keys_str.split(",")]


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get settings singleton instance

    Returns:
        Settings: Application settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
