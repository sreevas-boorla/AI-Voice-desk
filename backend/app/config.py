import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "VoiceDesk - CareBridge Clinic"
    CLINIC_NAME: str = "CareBridge Clinic"
    CLINIC_LOCATION: str = "Jubilee Hills, Hyderabad, Telangana"
    CLINIC_ADDRESS: str = "Road No. 36, Jubilee Hills, Hyderabad, Telangana 500033"
    CLINIC_PHONE: str = "+91 40 4960 8800"
    CLINIC_TIMEZONE: str = "Asia/Kolkata"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./voicedesk.db")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "carebridge-voicedesk-secret-key-2026-secure")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    
    # Default Admin
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "CareBridge2026!")
    
    # LiveKit Voice Credentials
    LIVEKIT_URL: str = os.getenv("LIVEKIT_URL", "")
    LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY", "")
    LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET", "")
    
    # LLM & AI Providers
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_TIMEOUT_SECONDS: float = float(os.getenv("GROQ_TIMEOUT_SECONDS", "30.0"))
    
    # Optional unverified providers (not advertised as working live)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Demo & Rate Limiting
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    CORS_ORIGINS: List[str] = [
        "http://localhost:5180",
        "http://127.0.0.1:5180",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    class Config:
        env_file = (".env", "../.env")
        extra = "ignore"

    def validate_production_hardening(self):
        """Enforces production deployment security standards."""
        if self.ENVIRONMENT.lower() in ("production", "prod"):
            if self.SECRET_KEY == "carebridge-voicedesk-secret-key-2026-secure":
                raise ValueError("Production environment cannot start with default insecure SECRET_KEY.")
            if self.ADMIN_PASSWORD == "CareBridge2026!":
                raise ValueError("Production environment cannot start with default ADMIN_PASSWORD.")
            if self.DEMO_MODE:
                raise ValueError("DEMO_MODE must be disabled (false) in production.")

settings = Settings()
settings.validate_production_hardening()
