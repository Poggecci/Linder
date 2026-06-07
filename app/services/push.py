import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from pywebpush import webpush, WebPushException
from app.config import settings

logger = logging.getLogger("linder.push")

class PushClient:
    async def send_notification(self, subscription: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        raise NotImplementedError()

class ProductionPushClient(PushClient):
    def __init__(
        self,
        vapid_private_key: str = settings.VAPID_PRIVATE_KEY,
        vapid_claims_email: str = settings.VAPID_CLAIMS_EMAIL
    ):
        self.vapid_private_key = vapid_private_key
        self.vapid_claims = {"sub": vapid_claims_email}

    def _send_sync(self, subscription_info: Dict[str, Any], data_str: str) -> None:
        """
        Synchronous execution of pywebpush.
        """
        webpush(
            subscription_info=subscription_info,
            data=data_str,
            vapid_private_key=self.vapid_private_key,
            vapid_claims=self.vapid_claims
        )

    async def send_notification(self, subscription: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        """
        Wraps synchronous pywebpush.webpush call in a thread pool to avoid blocking FastAPI's main thread.
        """
        if not self.vapid_private_key:
            logger.error("VAPID private key is not configured. Web Push notifications disabled.")
            return False

        subscription_info = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"]
            }
        }
        
        data_str = json.dumps(payload)
        
        try:
            logger.info(f"Sending Web Push to {subscription['user_id']} via endpoint {subscription['endpoint'][:50]}...")
            # Run the synchronous pywebpush in a thread pool executor
            await asyncio.to_thread(self._send_sync, subscription_info, data_str)
            logger.info(f"Web Push sent successfully to {subscription['user_id']}")
            return True
        except WebPushException as e:
            logger.error(f"WebPushException sending notification to {subscription['user_id']}: {e}")
            # WebPushException exposes the response object from the push service
            if e.response is not None:
                logger.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending push notification to {subscription['user_id']}: {e}")
            return False

class MockPushClient(PushClient):
    """
    Mock PushClient that intercepts deliveries and stores them in an in-memory array for test assertions.
    """
    def __init__(self):
        self.deliveries: List[Dict[str, Any]] = []

    async def send_notification(self, subscription: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        delivery = {
            "user_id": subscription.get("user_id"),
            "subscription_id": subscription.get("id"),
            "endpoint": subscription.get("endpoint"),
            "payload": payload
        }
        self.deliveries.append(delivery)
        logger.info(f"Mock push notification logged for user {subscription.get('user_id')}: {payload}")
        return True

    def clear(self):
        self.deliveries.clear()
