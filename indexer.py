import asyncio
import aiohttp
import logging
from typing import List
from urllib.parse import urlparse

from google.oauth2 import service_account
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ==========================================
# 1. DOMAIN EXCEPTIONS
# ==========================================
class TransientError(Exception):
    """Network blips, 429 Rate Limits, 500+ Server Errors. Retry these."""
    pass


class FatalError(Exception):
    """400 Bad Request, 401/403 Auth, 404. Do not retry."""
    pass

# ==========================================
# 2. INDEXING ENGINE
# ==========================================
class IndexingEngine:
    """
    High-performance, non-blocking Multi-Search Engine Indexing client.
    Supports Google (OAuth2), Bing (API Key), and Yandex (OAuth).
    """

    def __init__(self, google_creds, sc_service, bing_api_key: str, host: str, yandex_token: str):
        self.google_endpoint = "https://indexing.googleapis.com/v3/urlNotifications:publish"
        self.bing_endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrl?apikey={bing_api_key}"
        self.bing_api_key = bing_api_key
        self.host = host
        self.yandex_token = yandex_token
        self.google_creds = google_creds
        self.sc_service = sc_service
        self.logger = None # Initialized in create

    @classmethod
    async def create(cls, google_key_path: str, bing_api_key: str, host: str, yandex_token: str):
        """Async factory: offloads blocking credential load + service build to a thread."""
        logger = logging.getLogger(__name__)
        def _init_google():
            scopes = [
                "https://www.googleapis.com/auth/indexing",
                "https://www.googleapis.com/auth/webmasters.readonly"
            ]
            creds = service_account.Credentials.from_service_account_file(
                google_key_path, scopes=scopes
            )
            svc = build('searchconsole', 'v1', credentials=creds)
            return creds, svc

        try:
            google_creds, sc_service = await asyncio.to_thread(_init_google)
        except Exception as e:
            logger.critical(f"Google Service Account Failure: {str(e)}")
            raise
        instance = cls(google_creds, sc_service, bing_api_key, host, yandex_token)
        instance.logger = logger
        return instance

    async def inspect_rich_results(self, url: str):
        """
        Queries the Search Console URL Inspection API.
        Returns the verdict for Rich Results (Schema).
        """
        request_body = {
            'inspectionUrl': url,
            'siteUrl': self.host,  # Must match your GSC property exactly
            'languageCode': 'en-US'
        }

        # Offload the blocking Google API call to a thread
        def _execute():
            return self.sc_service.urlInspection().index().inspect(body=request_body).execute()

        try:
            response = await asyncio.to_thread(_execute)
            result = response.get('inspectionResult', {})

            # Extract Rich Results Data
            rich_results = result.get('richResultsResult', {})
            verdict = rich_results.get('verdict', 'NO_RICH_RESULTS_FOUND')

            # Log specific items (BlogPosting, FAQ, etc.)
            items = rich_results.get('detectedItems', [])
            for item in items:
                self.logger.info(f"🔍 Detected Schema: {item['richResultType']} - Status: {item['verdict']}")

            return verdict
        except Exception as e:
            self.logger.error(f"❌ Inspection Failure: {str(e)}")
            return "ERROR"

    async def _get_google_token(self) -> str:
        if not self.google_creds.valid:
            def _refresh():
                from google.auth.transport.requests import Request as SyncRequest
                self.google_creds.refresh(SyncRequest())
            await asyncio.to_thread(_refresh)
        return self.google_creds.token

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry=retry_if_exception_type(TransientError))
    async def notify_yandex(self, session: aiohttp.ClientSession, url: str):
        """Yandex Webmaster API Vyuha."""
        if not self.yandex_token:
            return True  # Skip gracefully if not configured

        headers = {"Authorization": f"OAuth {self.yandex_token}", "Content-Type": "application/json"}

        try:
            # 1. Fetch User ID
            async with session.get("https://api.webmaster.yandex.net/v4/user", headers=headers) as r:
                r.raise_for_status()
                user_id = (await r.json())['user_id']

            # 2. Fetch Host ID
            async with session.get(f"https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/", headers=headers) as r:
                r.raise_for_status()
                hosts_data = await r.json()

                # Robustly match host by netloc
                target_netloc = urlparse(self.host).netloc
                host_id = next((h['host_id'] for h in hosts_data.get('hosts', []) if urlparse(h.get('ascii_host_url', '')).netloc == target_netloc), None)

                if not host_id:
                    self.logger.error(f"❌ Yandex: Host not found for {self.host}")
                    return None

            # 3. Post to Recrawl Queue
            endpoint = f"https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/recrawl/queue"
            async with session.post(endpoint, headers=headers, json={"url": url}) as r:
                if r.status == 202:
                    self.logger.info(f"✅ Yandex: Acknowledged {url}")
                    return True
                elif r.status == 429:
                    raise TransientError("Yandex Recrawl Quota/Rate Limit Exceeded")
                else:
                    self.logger.error(f"❌ Yandex Failure: {r.status} - {await r.text()}")
                    r.raise_for_status()
                    return None

        except aiohttp.ClientError as e:
            raise TransientError(f"Yandex Network Error: {e}")
        except Exception as e:
            self.logger.error(f"💀 Yandex Error: {str(e)}")
            raise FatalError(f"Yandex API Error: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry=retry_if_exception_type(TransientError))
    async def notify_google(self, session: aiohttp.ClientSession, url: str):
        """Google Indexing API Vyuha."""
        token = await self._get_google_token()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        payload = {"url": url, "type": "URL_UPDATED"}

        try:
            async with session.post(self.google_endpoint, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    self.logger.info(f"✅ Google: Acknowledged {url}")
                    return True
                self.logger.error(f"❌ Google Failure: {resp.status} - {await resp.text()}")
                resp.raise_for_status()
                return None
        except aiohttp.ClientError as e:
            raise TransientError(f"Google Network Error: {e}")
        except Exception as e:
            self.logger.error(f"💀 Google Error: {str(e)}")
            raise FatalError(f"Google API Error: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry=retry_if_exception_type(TransientError))
    async def notify_bing(self, session: aiohttp.ClientSession, url: str):
        """Bing Webmaster API Vyuha."""
        # Bing uses a simple API Key in the URL params
        headers = {"Content-Type": "application/json; charset=utf-8"}
        payload = {
            "siteUrl": self.host,
            "url": url
        }

        try:
            async with session.post(url=self.bing_endpoint, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    self.logger.info(f"✅ Bing: Acknowledged {url}")
                    return True
                self.logger.error(f"❌ Bing Failure: {resp.status} - {await resp.text()}")
                resp.raise_for_status()
                return None
        except aiohttp.ClientError as e:
            raise TransientError(f"Bing Network Error: {e}")
        except Exception as e:
            self.logger.error(f"💀 Bing Error: {str(e)}")
            raise FatalError(f"Bing API Error: {e}")

    async def notify_all(self, url: str):
        """
        Parallel execution of multi-engine indexing.
        Returns a summary tuple for the distribution pipeline.
        """
        async with aiohttp.ClientSession() as session:
            # Launch concurrently to protect latency
            results = await asyncio.gather(
                self.notify_google(session, url),
                self.notify_bing(session, url),
                self.notify_yandex(session, url),
                return_exceptions=True
            )
            
            engines: List[str] = ["Google", "Bing", "Yandex"]
            for idx, r in enumerate(results):
                if isinstance(r, Exception):
                    self.logger.error(f"💀 {engines[idx]} Indexing Pipeline threw Exception: {type(r).__name__} - {str(r)}")

            # Filter and evaluate
            success: bool = all([not isinstance(r, Exception) and r is True for r in results])
            return "indexing-engine", "success" if success else "partial-fail"
