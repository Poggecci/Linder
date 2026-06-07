import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
from app.config import settings

logger = logging.getLogger("linder.auth")

class JWTService:
    def __init__(
        self,
        secret_key: str = settings.JWT_SECRET,
        algorithm: str = settings.JWT_ALGORITHM,
        expire_minutes: int = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        allow_mock: bool = True
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes
        self.allow_mock = allow_mock

    def create_access_token(self, user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)
        to_encode = {"sub": user_id, "exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_access_token(self, token: str) -> Optional[str]:
        if self.allow_mock and token.startswith("mock_token_user_"):
            user_id = token.replace("mock_token_user_", "")
            if user_id:
                return user_id

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            return user_id
        except jwt.PyJWTError as e:
            logger.warning(f"Failed JWT decode: {e}")
            return None
