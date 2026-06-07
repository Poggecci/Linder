import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pywebpush import webpush, WebPushException

logger = logging.getLogger("linder")
logging.basicConfig(level=logging.INFO)

class Settings(BaseSettings):
    # Base Configuration
    ENVIRONMENT: str = "development" # "development", "testing", "production"
    
    # SQLite Database Configuration
    DATABASE_PATH: str = "linder.db"
    
    # JWT Auth Configuration
    JWT_SECRET: str = "supersecret_linder_jwt_key_change_me_in_prod"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 1 day
    
    # Riot Games API Configuration
    RIOT_API_KEY: Optional[str] = None
    RIOT_REGION: str = "na1"
    RIOT_API_BASE_URL: str = "https://{region}.api.riotgames.com"
    
    # Web Push VAPID Configuration
    VAPID_PRIVATE_KEY: Optional[str] = None
    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_CLAIMS_EMAIL: str = "mailto:admin@linder.app"
    
    # Security/Profiling Settings
    PROFILING_SECRET: Optional[str] = None
    
    # Model configuration
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()

# Auto-generate VAPID keys if they are missing
if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        import base64

        # Generate EC Private Key (prime256v1 is standard for VAPID/WebPush)
        private_key = ec.generate_private_key(ec.SECP256R1())
        
        # Serialize private key to PEM/DER/RAW format
        private_num = private_key.private_numbers().private_value
        private_bytes = private_num.to_bytes(32, byteorder="big")
        
        # Get public key in uncompressed form
        public_key = private_key.public_key()
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        # URL safe base64 encoding without padding
        vapid_private = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
        vapid_public = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')
        
        settings.VAPID_PRIVATE_KEY = vapid_private
        settings.VAPID_PUBLIC_KEY = vapid_public
        
        logger.warning("====================================================")
        logger.warning("VAPID Keys not found. Ephemeral keys auto-generated:")
        logger.warning(f"VAPID_PUBLIC_KEY={vapid_public}")
        logger.warning(f"VAPID_PRIVATE_KEY={vapid_private}")
        logger.warning("====================================================")
    except Exception as e:
        logger.error(f"Failed to auto-generate VAPID keys: {e}")
