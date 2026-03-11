from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Application Settings
    app_name: str = "Production Agent API"
    environment: str = "development"
    debug: bool = True
    api_version: str = "v1"
    
    # Server Configuration
    host: str = "127.0.0.1"
    port: int = 8000
    
    # NetSuite API Configuration
    netsuite_account_id: str
    netsuite_realm: str
    netsuite_consumer_key: str
    netsuite_consumer_secret: str
    netsuite_token_id: str
    netsuite_token_secret: str
    netsuite_base_url: str
    
    # Security Settings
    secret_key: str = "GZ2P8yec4crIdEDWpj57WeFBCd6-30kF-8K2aXb7ziA"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Database
    database_url: str = "postgresql+asyncpg://goldfinger:goldfinger@localhost:5432/goldfinger"
    
    # ============================================================================
    # LOGGING
    # ============================================================================
    log_format: str = "json"
    
    @property
    def log_level(self) -> str:
        """Return appropriate log level based on environment"""
        levels = {
            "development": "DEBUG",
            "staging": "INFO",
            "production": "WARNING"
        }
        return levels.get(self.environment.lower(), "INFO")
    
    # CORS Settings
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def cors_origins(self) -> List[str]:
        """Parse comma-separated origins string into list"""
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    def get_netsuite_auth_headers(self) -> dict:
        """Helper method to get NetSuite authentication headers"""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


# Create a global settings instance
settings = Settings()


# Validation on startup
def validate_settings():
    """Validate required settings on application startup"""
    required_netsuite_fields = [
        "netsuite_account_id",
        "netsuite_realm", 
        "netsuite_consumer_key",
        "netsuite_consumer_secret",
        "netsuite_token_id",
        "netsuite_token_secret",
        "netsuite_base_url"
    ]
    
    missing_fields = []
    for field in required_netsuite_fields:
        if not getattr(settings, field, None):
            missing_fields.append(field.upper())
    
    if missing_fields:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_fields)}")
    
    # ============================================================================
    # PRODUCTION SAFETY CHECKS
    # ============================================================================
    if settings.is_production:
        # Check secret key in production against the actual hardcoded default
        if settings.secret_key == "GZ2P8yec4crIdEDWpj57WeFBCd6-30kF-8K2aXb7ziA":
            raise ValueError(
                "SECURITY ERROR: You must change SECRET_KEY in production! "
                "Generate a new key with: openssl rand -hex 32"
            )
        # Ensure debug is off
        if settings.debug:
            raise ValueError(
                "⚠️  SECURITY ERROR: DEBUG must be False in production! "
                "Set DEBUG=false in your .env file"
            )
    
    print(f"✅ Configuration loaded successfully for {settings.app_name}")
    print(f"🌍 Environment: {settings.environment}")
    print(f"📊 Log Level: {settings.log_level}")


if __name__ == "__main__":
    # Test configuration loading
    try:
        validate_settings()
        print("Configuration is valid!")
    except Exception as e:
        print(f"Configuration error: {e}")