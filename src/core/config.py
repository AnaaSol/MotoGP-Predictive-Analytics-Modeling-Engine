from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Database Settings
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    
    # App Settings
    PROJECT_NAME: str = "MotoGP Predictive Engine"
    ENVIRONMENT: str = "development"
    
    # Scraper Settings (for future use)
    SCRAPER_USER_AGENT: str = "MotoGP-Analytics-Bot/1.0"
    
    # Pydantic configuration to read from .env file
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()