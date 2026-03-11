import json
import asyncio
import logging
import random
import time
from typing import Dict, Any, Optional

import httpx
from requests_oauthlib import OAuth1
from requests import Request as Req

from app.config import settings

logger = logging.getLogger(__name__)


class NetSuiteService:
    """Async NetSuite API service with connection pooling, retries, and rate limiting."""

    # Class-level persistent client and semaphore
    _client: Optional[httpx.AsyncClient] = None
    _semaphore: Optional[asyncio.Semaphore] = None

    # Metrics
    _total_requests: int = 0
    _total_errors: int = 0
    _total_retries: int = 0
    _rate_limit_hits: int = 0

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

    @classmethod
    async def startup(cls):
        """Initialize persistent HTTP client and semaphore. Call on app startup."""
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            logger.info("NetSuite HTTP client initialized (max_connections=20, keepalive=10)")
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(5)
            logger.info("NetSuite concurrency semaphore initialized (max=5)")

    @classmethod
    async def shutdown(cls):
        """Close persistent HTTP client. Call on app shutdown."""
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
            logger.info("NetSuite HTTP client closed")

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Return current metrics counters."""
        return {
            "total_requests": cls._total_requests,
            "total_errors": cls._total_errors,
            "total_retries": cls._total_retries,
            "rate_limit_hits": cls._rate_limit_hits,
        }

    async def execute_suiteql(self, query: str, max_retries: int = 3) -> Dict[str, Any]:
        start_time = time.time()
        payload = json.dumps({"q": query})

        # Ensure client is ready (lazy init for safety)
        if self.__class__._client is None:
            await self.__class__.startup()

        semaphore = self.__class__._semaphore

        for attempt in range(max_retries):
            async with semaphore:
                try:
                    # Re-sign each attempt (OAuth nonce/timestamp must be fresh)
                    req = Req(
                        method="POST",
                        url=self.base_url,
                        headers={"Content-Type": "application/json", "Prefer": "transient"},
                        data=payload,
                    )
                    prepared = req.prepare()
                    signed = self.oauth(prepared)

                    self.__class__._total_requests += 1

                    response = await self.__class__._client.request(
                        method=signed.method,
                        url=signed.url,
                        headers=dict(signed.headers),
                        content=signed.body,
                    )

                    # Handle rate limiting (429)
                    if response.status_code == 429:
                        self.__class__._rate_limit_hits += 1
                        retry_after = int(response.headers.get("Retry-After", "60"))
                        logger.warning(
                            f"NetSuite rate limit hit (429). Waiting {retry_after}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            self.__class__._total_retries += 1
                            await asyncio.sleep(retry_after)
                            continue
                        response.raise_for_status()

                    # Retry on 5xx
                    if response.status_code >= 500:
                        self.__class__._total_errors += 1
                        if attempt < max_retries - 1:
                            backoff = (1 * (2 ** attempt)) + random.uniform(0, 0.5)
                            self.__class__._total_retries += 1
                            logger.warning(
                                f"NetSuite 5xx ({response.status_code}). "
                                f"Retrying in {backoff:.1f}s (attempt {attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(backoff)
                            continue
                        response.raise_for_status()

                    # 4xx (non-429) — fail immediately
                    response.raise_for_status()

                    data = response.json()
                    elapsed = time.time() - start_time
                    logger.info(
                        f"[TIMING] NetSuite query took {elapsed:.3f}s, "
                        f"returned {len(data.get('items', []))} rows"
                    )
                    return data

                except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                    self.__class__._total_errors += 1
                    if attempt < max_retries - 1:
                        backoff = (1 * (2 ** attempt)) + random.uniform(0, 0.5)
                        self.__class__._total_retries += 1
                        logger.warning(
                            f"NetSuite connection error: {e}. "
                            f"Retrying in {backoff:.1f}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(backoff)
                        continue
                    logger.error(f"NetSuite request failed after {max_retries} attempts: {e}")
                    raise

        # Should not reach here, but just in case
        raise httpx.HTTPError(f"NetSuite request failed after {max_retries} attempts")
