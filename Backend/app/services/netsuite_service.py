import json
import logging
import time
from typing import Dict, Any

import httpx
from requests_oauthlib import OAuth1
from requests import Request as Req

from app.config import settings

logger = logging.getLogger(__name__)

class NetSuiteService:
    """Async NetSuite API service - handles SuiteQL execution"""

    def __init__(self):
        self.base_url = settings.netsuite_base_url
        self.account_id = settings.netsuite_account_id
        self.realm = settings.netsuite_realm
        self.consumer_key = settings.netsuite_consumer_key
        self.consumer_secret = settings.netsuite_consumer_secret
        self.token_id = settings.netsuite_token_id
        self.token_secret = settings.netsuite_token_secret

        self.oauth = OAuth1(
            self.consumer_key,
            self.consumer_secret,
            self.token_id,
            self.token_secret,
            signature_method="HMAC-SHA256",
            realm=self.realm,
        )

    async def execute_suiteql(self, query: str) -> Dict[str, Any]:
        start_time = time.time()
        payload_dict = {"q": query}
        payload = json.dumps(payload_dict)  # Corrected here to use json.dumps

        req = Req(
            method="POST",
            url=self.base_url,
            headers={"Content-Type": "application/json", "Prefer": "transient"},
            data=payload
        )

        prepared = req.prepare()
        signed = self.oauth(prepared)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=signed.method,
                url=signed.url,
                headers=dict(signed.headers),
                content=signed.body  # JSON string bytes
            )

        response.raise_for_status()
        data = response.json()
        elapsed = time.time() - start_time
        logger.info(f"[TIMING] NetSuite query took {elapsed:.3f}s, returned {len(data.get('items', []))} rows")
        return data
