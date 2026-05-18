# ==========================================
# 🛡️ THE ARMORY (Configuration & Keys)
# ==========================================
import textwrap
import os
from dotenv import load_dotenv


os.environ.setdefault('HF_HOME', os.path.join(os.path.expanduser("~"), ".cache", "huggingface"))
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Coroutine, Union
import trafilatura

load_dotenv()

from googleapiclient.discovery import build
try:
    from content_gen import write_the_content_31b, _normalize_for_echo_check
except ImportError:
    from engine.content_gen import write_the_content_31b, _normalize_for_echo_check


@dataclass(frozen=True)
class PublisherConfig:
    # API Keys & Tokens
    DEVTO_API_KEY: str
    HASHNODE_TOKEN: str
    HASHNODE_PUB_ID: str
    DISCORD_WEBHOOK: str
    LINKEDIN_ACCESS_TOKEN: str
    MASTODON_CLIENT_KEY :  str
    MASTODON_CLIENT_SECRET : str
    LINKEDIN_PERSON_ID: str
    NOSTR_PUBLIC_ID : str
    BLUESKY_HANDLE: str
    BLUESKY_APP_PASSWORD: str
    MASTODON_ACCESS_TOKEN: str
    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: str
    GOOGLE_API_KEY: str
    BING_API: str
    PSI_API: str
    PARAGRAPH_API_KEY : str
    NOSTR_PRIVATE_ID : str
    TUMBLR_CONSUMER_KEY: str
    TUMBLR_CONSUMER_SECRET: str
    TUMBLR_OAUTH_TOKEN: str
    TUMBLR_OAUTH_SECRET: str
    TUMBLR_BLOG_NAME: str

    # URLs & Identifiers
    BLOGGER_URL: str
    MASTODON_INSTANCE_URL: str
    LINKEDIN_POST_AUTHOR_URN: str

    # Yandex Specifics
    YANDEX_CLIENT_ID: str
    YANDEX_CLIENT_SECRET: str
    YANDEX_CODE: str

    #ranking
    OPR_API_KEY: str  # DomCop Open PageRank
    DOMAIN_TO_CHECK: str = os.getenv("BLOG_DOMAIN", "example.com")

    # Optional / Defaulted Settings
    TAGS: List[str] = field(default_factory=lambda: ["programming", "tech"])
    DRY_RUN: bool = False
    RE_TEST_ON_RETRY: bool = False
    CHECK_TITLE_ONLY: bool = False




    # Nested Dicts
    PSI_THRESHOLDS: Dict[str, float] = field(default_factory=lambda: {
        "performance": 90,
        "accessibility": 90,
        "best-practices": 90,
        "seo": 90
    })

CONFIG: PublisherConfig = PublisherConfig(
    DEVTO_API_KEY=os.getenv("DEVTO_API_KEY", ""),
    HASHNODE_TOKEN=os.getenv("HASHNODE_TOKEN", ""),
    HASHNODE_PUB_ID=os.getenv("HASHNODE_PUB_ID", ""),
    DISCORD_WEBHOOK=os.getenv("DISCORD_WEBHOOK", ""),
    TAGS=['Systems-Design', 'Infrastructure', 'Technical-Analysis', 'Engineering-Ops'],
    BLOGGER_URL=os.getenv("BLOGGER_URL", "https://example.blogspot.com"),
    LINKEDIN_ACCESS_TOKEN=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
    LINKEDIN_PERSON_ID=os.getenv("LINKEDIN_PERSON_ID", ""),
    LINKEDIN_POST_AUTHOR_URN=os.getenv("LINKEDIN_POST_AUTHOR_URN", ""),
    BLUESKY_HANDLE=os.getenv("BLUESKY_HANDLE", ""),
    BLUESKY_APP_PASSWORD=os.getenv("BLUESKY_APP_PASSWORD", ""),
    MASTODON_ACCESS_TOKEN=os.getenv("MASTODON_ACCESS_TOKEN", ""),
    MASTODON_INSTANCE_URL=os.getenv("MASTODON_INSTANCE_URL", "https://mastodon.social"),
    MASTODON_CLIENT_KEY=os.getenv("MASTODON_CLIENT_KEY", ""),
    MASTODON_CLIENT_SECRET=os.getenv("MASTODON_CLIENT_SECRET", ""),
    BING_API=os.getenv("BING_API", ""),
    PSI_API=os.getenv("PSI_API", ""),
    YANDEX_CLIENT_ID=os.getenv("YANDEX_CLIENT_ID", ""),
    YANDEX_CLIENT_SECRET=os.getenv("YANDEX_CLIENT_SECRET", ""),
    TELEGRAM_TOKEN=os.getenv("TELEGRAM_TOKEN", ""),
    TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID", ""),
    YANDEX_CODE=os.getenv("YANDEX_CODE", ""),
    GOOGLE_API_KEY=os.getenv("GOOGLE_API_KEY", ""),
    PSI_THRESHOLDS={'performance': 95.0, 'accessibility': 85.0, 'best-practices': 90.0, 'seo': 90.0},
    NOSTR_PUBLIC_ID=os.getenv("NOSTR_PUBLIC_ID", ""),
    NOSTR_PRIVATE_ID=os.getenv("NOSTR_PRIVATE_ID", ""),
    OPR_API_KEY=os.getenv("OPR_API_KEY", ""),
    PARAGRAPH_API_KEY=os.getenv("PARAGRAPH_API_KEY", ""),
    TUMBLR_CONSUMER_KEY=os.getenv("TUMBLR_CONSUMER_KEY", ""),
    TUMBLR_CONSUMER_SECRET=os.getenv("TUMBLR_CONSUMER_SECRET", ""),
    TUMBLR_OAUTH_TOKEN=os.getenv("TUMBLR_OAUTH_TOKEN", ""),
    TUMBLR_OAUTH_SECRET=os.getenv("TUMBLR_OAUTH_SECRET", ""),
    TUMBLR_BLOG_NAME=os.getenv("TUMBLR_BLOG_NAME", ""),
    CHECK_TITLE_ONLY=(os.getenv("CHECK_TITLE_ONLY", "false").lower() == "true")
)

#=======================================================
#COPY PASTE OR READ UNTIL HERE FROM BOTTOM
#=======================================================

import asyncio
import aiohttp
import hashlib
import json
import os
import urllib.parse
import queue
import logging
from logging.handlers import QueueHandler, QueueListener
import aiofiles
from google.oauth2 import service_account
from markdownify import markdownify
from selectolax.lexbor import LexborHTMLParser
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type, retry
from aiohttp import DummyCookieJar
from typing import Any
from atproto import AsyncClient
from atproto.exceptions import AtProtocolError
from mastodon import Mastodon, MastodonNetworkError, MastodonAPIError
from playwright.async_api import async_playwright
from axe_playwright_python.async_playwright import Axe
from nostr_sdk import  Keys, RelayUrl, EventBuilder, NostrSigner, ClientBuilder
import math


timeout = aiohttp.ClientTimeout(total=15)


# ==========================================
# 1. DOMAIN EXCEPTIONS
# ==========================================
class TransientError(Exception):
    """Network blips, 429 Rate Limits, 500+ Server Errors. Retry these."""
    pass


class FatalError(Exception):
    """400 Bad Request, 401/403 Auth, 404. Do not retry."""
    pass

from dataclasses import replace

@dataclass(frozen=True)
class PostData:
    title: str
    markdown_body: str
    canonical_url: str
    post_summary: str
    html_content: str
    image_url: str | None = None
    ai_hook: str | None = None
    dynamic_tags: list[str] | None = None
    syndicated_body: str | None = None

# ==========================================
# 2. NON-BLOCKING LOGGING
# ==========================================
log_queue: queue.Queue = queue.Queue(-1)
queue_handler: logging.handlers.QueueHandler = QueueHandler(log_queue)
stream_handler: logging.StreamHandler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
log_listener: logging.handlers.QueueListener = QueueListener(log_queue, stream_handler)

logger: logging.Logger = logging.getLogger("publisher")
logger.addHandler(queue_handler)
logger.setLevel(logging.INFO)

# ==========================================
# 3. SMART RETRY ENGINE
# ==========================================
retrier: AsyncRetrying = AsyncRetrying(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(TransientError),
    reraise=True
)

# ==========================================
# 4. STATE MANAGER (Idempotency)
# ==========================================
STATE_FILE: str = "publisher_state.json"


async def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            async with aiofiles.open(STATE_FILE, "r") as f:
                content: str = await f.read()
                return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("State file corrupted. Rebuilding.")
    return {
        "current_hash": None,
        "platforms": {},
        "ai_hook": None   # ✅ NEW
    }



# 1. Instantiate the lock globally so all concurrent tasks share the same instance.
STATE_LOCK: asyncio.Lock = asyncio.Lock()

async def save_state(state: Dict[str, Any]) -> None:
    async with STATE_LOCK:
        tmp: str = STATE_FILE + ".tmp"
        try:
            async with aiofiles.open(tmp, "w") as f:
                await f.write(json.dumps(state, indent=4))
            os.replace(tmp, STATE_FILE)  # atomic rename — CPU-instant, no thread needed
        except PermissionError:
            logger.error(f"PERMISSION NOT GRANTED. Failed to write state: {state}")
        except Exception as e:
            logger.error(f"Disk I/O error while saving state: {e} | State: {state}")


def _extract_blogger_image(parser: LexborHTMLParser) -> Optional[str]:
    """
    Uses Lexbor to accurately find the first Blogger-hosted image.
    """
    logger.info("🔍 [HELPER] Parsing HTML with Lexbor for cover image...")


    # Find all img tags
    for img in parser.css("img"):
        src: Optional[str] = img.attributes.get("src")
        if src and "blogger.googleusercontent.com" in src:
            # Clean the URL (remove Blogger's resizing parameters if needed)
            # e.g., =w400-h400 at the end
            clean_url: str = src.split('=')[0] if '=' in src else src
            logger.info(f"📸 [HELPER] Lexbor found image: {clean_url}...")
            return clean_url

    logger.warning("⚠️ [HELPER] Lexbor found no matching Blogger images.")
    return None


async def fetch_open_pagerank(session: aiohttp.ClientSession, api_key: str, domain: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Fetches PageRank & Global Rank via DomCop's Open PageRank API.
    Returns a dict with 'score' and 'rank', or None if it fails.
    """
    url: str = "https://openpagerank.com/api/v1.0/getPageRank"
    headers: Dict[str, str] = {"API-OPR": api_key}

    # The API expects an array of domains
    params: Dict[str, List[str]] = {"domains[]": [domain]}

    try:
        async with session.get(url, headers=headers, params=params, timeout=10) as resp:
            if resp.status == 200:
                data: Dict[str, Any] = await resp.json()

                # DomCop returns data inside a 'response' list
                results: List[Dict[str, Any]] = data.get("response", [])
                if results and results[0].get("status_code") == 200:
                    score: float = results[0].get("page_rank_decimal", 0)
                    rank: str = results[0].get("rank", "N/A")

                    return score, rank

            logger.warning(f"⚠️ OPR API Error: HTTP {resp.status}")
            return None, None

    except Exception as e:
        logger.error(f"❌ OPR Connection failed: {e}")
        return None, None

# ==========================================
# 5. HELPERS
# ==========================================
def smart_truncate(html: str) -> Optional[str]:
    parser: LexborHTMLParser = LexborHTMLParser(html)

    paragraphs: List[Any] = [p for p in parser.tags("p") if p.text(strip=True)]
    if not paragraphs:
        return None

    h1: List[Any] = parser.tags("h1")
    nav: List[Any] = parser.css('nav[aria-label="Table of Contents"]')

    # helper: DOM position comparator via index fallback
    def appears_after(a: Any, b: Any) -> bool:
        return html.find(str(a)) > html.find(str(b))

    # -------------------------
    # fallback 1: after TOC nav
    # -------------------------
    if nav:
        nav_node: Any = nav[0]
        for p in paragraphs:
            if appears_after(p, nav_node):
                return p.text(strip=True)

    # -------------------------
    # fallback 2: after h1
    # -------------------------
    if h1:
        h1_node: Any = h1[0]
        for p in paragraphs:
            if appears_after(p, h1_node):
                text: str = p.text(strip=True)
                if len(text) > 40:
                    return text

    # -------------------------
    # fallback 3: first meaningful paragraph
    # -------------------------
    for p in paragraphs:
        text: str = p.text(strip=True)
        if len(text) > 40:
            return text

    return None

def build_utm_url(base_url: str, platform: str) -> str:
    """Generates a tracked URL to monitor platform performance."""
    params: Dict[str, str] = {"utm_source": platform, "utm_medium": "social", "utm_campaign": "dharma_engine"}
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def compute_content_hash(post_data: PostData) -> str:
    hasher: Any = hashlib.sha256()
    unique_string: str = f"{post_data.canonical_url}::{post_data.markdown_body}"
    hasher.update(unique_string.encode("utf-8"))
    return hasher.hexdigest()


def fallback_teaser(html_content: str, ai_hook: str) -> str:
    """Ultimate Fallback: Hook + One Code Block + Link."""
    parser: LexborHTMLParser = LexborHTMLParser(html_content)
    code_block_md: str = ""

    # Try to find the first code block in the HTML
    pre_tags: List[Any] = parser.tags("pre")
    if pre_tags:
        code_text: str = pre_tags[0].text(strip=True)
        # Cap length just in case it's a massive block of logs or JSON
        if len(code_text) > 1000:
            code_text = code_text[:1000] + "\n... [Code Truncated]"
        code_block_md = f"\n\n```text\n{code_text}\n```\n"

    return f"{ai_hook}\n{code_block_md}"


# ==========================================
# AI (REWRITTEN & LOG-HEAVY)
# ==========================================

_GEMMA_MODEL_CACHE: Dict[str, str] = {}

async def _get_gemma_model(session: aiohttp.ClientSession, requested_name: str, fallback_keywords: List[str]) -> str:
    cache_key = f"{requested_name}|{','.join(fallback_keywords)}"
    if cache_key in _GEMMA_MODEL_CACHE:
        return _GEMMA_MODEL_CACHE[cache_key]
    if not CONFIG.GOOGLE_API_KEY:
        raise FatalError("GOOGLE_API_KEY is required for Gemma generation.")

    models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={CONFIG.GOOGLE_API_KEY}"
    async with session.get(models_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            raise TransientError(f"Gemma model discovery failed: HTTP {resp.status} {await resp.text()}")
        data = await resp.json()

    available_models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
    gemma_models = [m for m in available_models if "gemma" in m.lower()]
    if requested_name in gemma_models:
        _GEMMA_MODEL_CACHE[cache_key] = requested_name
        return requested_name
    # Prioritize by size/rigor
    priority_order = ["31b", "27b", "26b", "9b", "7b", "2b"]
    for p in priority_order:
        for model in gemma_models:
            if p in model.lower():
                _GEMMA_MODEL_CACHE[cache_key] = model
                return model

    _GEMMA_MODEL_CACHE[cache_key] = gemma_models[0]
    return gemma_models[0]

async def _gemma_generate(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    requested_model: str = "gemma-4-26b-a4b-it",
    fallback_keywords: Optional[List[str]] = None,
    temperature: float = 0.4,
    timeout_seconds: int = 180,
    max_output_tokens: Optional[int] = None
) -> str:
    target_model = await _get_gemma_model(session, requested_model, fallback_keywords or ["26b", "27b", "31b"])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={CONFIG.GOOGLE_API_KEY}"
    generation_config: Dict[str, Any] = {"temperature": temperature}
    if max_output_tokens:
        generation_config["maxOutputTokens"] = max_output_tokens
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as resp:
        if resp.status != 200:
            raise TransientError(f"Gemma generation failed on {target_model}: HTTP {resp.status} {await resp.text()}")
        data: Dict[str, Any] = await resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

async def _draft_style(session: aiohttp.ClientSession, markdown_body: str, style_prompt: str, draft_id: int) -> Optional[str]:
    """Gemma hook drafter."""
    logger.info(f"🧠 [AI-DRAFT-{draft_id}] Initiating Gemma draft with style: '{style_prompt[:30]}...'")
    prompt = (
        f"{style_prompt}\n"
        "Write exactly ONE short, complete, punchy sentence for a technical audience. "
        "Max 200 characters. End with punctuation. No intro text.\n\n"
        f"Article:\n{markdown_body[:6000]}"
    )
    try:
        content = await _gemma_generate(session, prompt, requested_model="gemma-4-26b-a4b-it", fallback_keywords=["26b", "27b", "31b"], temperature=0.75, timeout_seconds=180)
        content = content.splitlines()[0].strip(' "\'')
        logger.info(f"✅ [AI-DRAFT-{draft_id}] Success. Draft length: {len(content)} chars.")
        return content
    except Exception as e:
        logger.error(f"❌ [AI-DRAFT-{draft_id}] Network Exception ({type(e).__name__}): {str(e) or 'No message'}")

    return None


async def _refine_best(session: aiohttp.ClientSession, drafts: List[Optional[str]], post_data: PostData) -> str:
    """
    The Editor: Fixes the 'terrible' tone and ensures sentences are complete.
    """
    valid_drafts: List[str] = [d for d in drafts if d is not None]
    if not valid_drafts:
        return post_data.post_summary or "New technical update."

    # Persona shift: Expert Content Editor to ensure high-engagement and clarity
    editor_instruction: str = (
        "You are a Technical Editor. Review the drafts and output ONE sharp hook. "
        "RULES:\n"
        "1. NO corporate jargon or AI buzzwords.\n"
        "2. Lead with a compelling technical hook.\n"
        "3. Output ONLY the hook sentence. No meta-commentary.\n"
    )

    try:
        hook = await _gemma_generate(
            session,
            f"{editor_instruction}\n\nDrafts:\n{chr(10).join(valid_drafts)}",
            requested_model="gemma-4-26b-a4b-it",
            fallback_keywords=["26b", "27b", "31b"],
            temperature=0.8,
            timeout_seconds=180,
        )
        hook = hook.splitlines()[0].strip(' "\'')
        if not any(hook.endswith(p) for p in ['.', '!', '?']):
            logger.warning(f"⚠️ [AI-EDITOR] Incomplete sentence detected: '{hook[:50]}...'. Retrying with first draft.")
            hook = valid_drafts[0]

        # Guard against title echoing
        if _normalize_for_echo_check(hook) == _normalize_for_echo_check(post_data.title):
            logger.warning("⚠️ [AI-EDITOR] Hook is an echo of the title. Forcing narrative redraft.")
            hook = await _gemma_generate(session, f"Write a VISCERAL opening sentence for this topic that is NOT the title: {post_data.title}", temperature=0.9)
            hook = hook.splitlines()[0].strip(' "\'')

        if len(hook) > 280:
            truncated: str = textwrap.shorten(hook, width=280, placeholder="...")
            logger.warning(f"✂️ [AI-EDITOR] Hook truncated from {len(hook)} to {len(truncated)} chars.")
            return truncated

        return hook
    except Exception as e:
        logger.error(f"❌ [AI-EDITOR] Refinement Exception ({type(e).__name__}): {str(e) or 'No message'}")

    return textwrap.shorten(valid_drafts[0] if valid_drafts else post_data.title, width=240, placeholder="...")


async def _generate_dynamic_tags(session: aiohttp.ClientSession, markdown_body: str) -> List[str]:
    """Gemma tag extractor."""
    logger.info("🧠 [AI-TAGS] Initiating dynamic tag extraction via Gemma...")
    is_short = len(markdown_body.split()) < 20
    if is_short:
        prompt = (
            f"Identify 3 deep-dive engineering categories for this topic: '{markdown_body}'.\n"
            "Output exactly 3 technical tags separated by commas. No symbols. No meta-talk.\n"
            "Example: thermodynamics,materials-science,urban-grids"
        )
    else:
        prompt = (
            "Output exactly 3 technical tags separated by commas. No symbols. No meta-talk. Output ONLY the tags.\n"
            "Good Example: python,async,fastapi\n\n"
            f"Source:\n{markdown_body[:4000]}"
        )
    try:
        content = await _gemma_generate(session, prompt, requested_model="gemma-4-26b-a4b-it", fallback_keywords=["4b", "26b", "27b"], temperature=0.1)
        
        # Guard against input echoing
        source_clean = _normalize_for_echo_check(markdown_body[:100])
        if _normalize_for_echo_check(content) in source_clean or "Constraint" in content:
            logger.warning("⚠️ [AI-TAGS] Model echoed input/constraint. Using hardcoded fallback.")
            return ["Tech", "Engineering", "Architecture"]

        tags: List[str] = [t.strip().replace("#", "").replace(" ", "") for t in content.replace("\n", ",").split(",") if t.strip()]
        final_tags: List[str] = tags[:3]
        logger.info(f"✅ [AI-TAGS] Extracted {len(final_tags)} tags: {final_tags}")
        return final_tags
    except Exception as e:
        logger.error(f"❌ [AI-TAGS] Network Exception ({type(e).__name__}): {str(e) or 'No message'}")

    logger.warning("⚠️ [AI-TAGS] Fallback triggered. Returning CONFIG.TAGS.")
    return CONFIG.TAGS if CONFIG.TAGS else ["Tech", "Programming", "Architecture"]


# ==========================================
# 5.5 SERP COMPETITOR ANALYZER
# ==========================================

async def _generate_search_query(session: aiohttp.ClientSession, title: str) -> str:
    logger.info("🧠 [AI-SERP] Generating search query via Gemma...")
    prompt = (
        "Convert this title into a technical search query. "
        "Output ONLY the query.\n\n"
        f"Title: {title}"
    )
    try:
        query = await _gemma_generate(session, prompt, requested_model="gemma-4-26b-a4b-it", fallback_keywords=["4b", "26b", "27b"], temperature=0.1)
        query = query.splitlines()[0].strip(' "\'')
        logger.info(f"✅ [AI-SERP] Generated Query: '{query}'")
        return query
    except Exception as e:
        logger.error(f"❌ [AI-SERP] Query Generation Exception ({type(e).__name__}): {str(e) or 'No message'}")
    return title

async def _fetch_organic_serp(session: aiohttp.ClientSession, query: str) -> List[str]:
    logger.info(f"🔍 [SERP] Fetching top 5 organic results for '{query}'...")
    api_key = os.getenv("SERPAPI_KEY", "")
    params = {"engine": "google", "q": query, "num": "5", "api_key": api_key}
    try:
        async with session.get("https://serpapi.com/search", params=params) as response:
            if response.status == 200:
                data = await response.json()
                links = [res.get("link") for res in data.get("organic_results", [])][:5]
                logger.info(f"✅ [SERP] Found {len(links)} organic results.")
                return [l for l in links if l]
    except Exception as e:
        logger.error(f"❌ [SERP] Fetch Exception: {e}")
    return []

async def _extract_competitor_texts(urls: List[str]) -> Dict[str, str]:
    def extract(urlx):
        downloaded = trafilatura.fetch_url(urlx)
        if downloaded:
            return trafilatura.extract(downloaded, include_links=False, include_images=False, include_tables=False)
        return None

    async def fetch_and_extract(url):
        logger.info(f"🕸️ [SERP] Extracting content from: {url}...")
        try:
            text = await asyncio.to_thread(extract, url)
            return url, text
        except Exception as e:
            logger.error(f"❌ [SERP] Trafilatura failed for {url}: {e}")
            return url, None

    results = await asyncio.gather(*(fetch_and_extract(url) for url in urls))
    return {url: text for url, text in results if text}

def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    return dot_product / (norm_v1 * norm_v2) if norm_v1 and norm_v2 else 0.0

class VectorCache:
    """A persistent cache for document vectors so we don't rerun ONNX on known URLs/Hashes."""
    def __init__(self, cache_file="vector_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load()

    def _load(self) -> Dict[str, List[float]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, OSError):
                return {}
        return {}

    def _save(self):
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f)

    def get(self, text_hash: str) -> Optional[List[float]]:
        return self.cache.get(text_hash)

    def set(self, text_hash: str, vector: List[float]):
        self.cache[text_hash] = vector
        self._save()

def get_text_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

class NomicEmbedder:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        logger.info("🧠 [AI-ONNX] Loading Nomic Embed v1.5 INT8 Model into memory...")
        import numpy as np
        import onnxruntime as ort
        from transformers import AutoTokenizer
        from huggingface_hub import hf_hub_download

        hf_token = os.environ.get('HF_TOKEN')
        if hf_token:
            logger.info("✅ Hugging Face token detected - using authenticated downloads (higher rate limits)")
        else:
            logger.warning("⚠️ No HF_TOKEN found - using unauthenticated downloads (rate limited)")

        # Set up Hugging Face cache directory to reuse downloaded models
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        os.makedirs(cache_dir, exist_ok=True)
        
        self.np = np
        self.model_id = "Xenova/nomic-embed-text-v1"
        
        # Cache properly by setting cache_dir argument
        logger.info(f"💾 Using Hugging Face cache directory: {cache_dir}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, 
            cache_dir=cache_dir,
            local_files_only=False  # Allow download on first run, then cache
        )  # type: ignore
        
        # Download with explicit cache directory
        model_path = hf_hub_download(
            repo_id=self.model_id, 
            filename="onnx/model_quantized.onnx",
            cache_dir=cache_dir
        )
        logger.info(f"✅ Model cached at: {model_path}")
        sess_options = ort.SessionOptions()
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, sess_options=sess_options, providers=['CPUExecutionProvider'])

    def embed(self, texts: List[str]) -> List[List[float]]:
        np = self.np
        encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors="np")
        
        inputs = {
            "input_ids": encoded["input_ids"].astype(np.int64),
            "attention_mask": encoded["attention_mask"].astype(np.int64),
            "token_type_ids": encoded["token_type_ids"].astype(np.int64)
        }
        
        outputs = self.session.run(None, inputs)
        token_embeddings = outputs[0]
        
        # Mean Pooling
        mask = encoded["attention_mask"]
        input_mask_expanded = np.expand_dims(mask, axis=-1).astype(float)
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)  # type: ignore
        sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)  # type: ignore
        # L2 Normalization
        pooled = sum_embeddings / sum_mask  # type: ignore
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / norms).tolist()

async def _compute_embeddings(_session: aiohttp.ClientSession, texts: List[str]) -> List[List[float]]:
    logger.info(f"🧠 [AI-SERP] Computing ONNX embeddings for {len(texts)} texts...")
    cache = VectorCache()
    results = []
    
    texts_to_embed = []
    indices_to_embed = []
    
    # Check cache first
    for i, text in enumerate(texts):
        text_hash = get_text_hash(text)
        cached_vec = cache.get(text_hash)
        if cached_vec:
            results.append(cached_vec)
        else:
            results.append(None) # Placeholder
            texts_to_embed.append(text)
            indices_to_embed.append(i)
            
    # Run ONNX for cache misses
    if texts_to_embed:
        embedder = NomicEmbedder.get_instance()
        # Nomic supports 8192 context natively!
        new_vectors = await asyncio.to_thread(embedder.embed, texts_to_embed)
        
        for idx, vec in zip(indices_to_embed, new_vectors):
            results[idx] = vec
            cache.set(get_text_hash(str(texts[idx])), vec)
            
    return results

async def _analyze_gaps_via_embeddings(session: aiohttp.ClientSession, my_text: str, comp_texts: Dict[str, str]) -> Dict[str, Any]:
    if not comp_texts:
        return {"lowest_urls": [], "competitor_scores": {}, "competitor_context": ""}

    urls = list(comp_texts.keys())
    texts_to_embed = [my_text] + [comp_texts[u] for u in urls]
    
    embeddings = await _compute_embeddings(session, texts_to_embed)
    if len(embeddings) != len(texts_to_embed):
        return {"lowest_urls": [], "competitor_scores": {}, "competitor_context": ""}
        
    my_emb = embeddings[0]
    comp_embs = embeddings[1:]
    
    scores = {}
    for i, u in enumerate(urls):
        similarity = _cosine_similarity(my_emb, comp_embs[i])
        rank_position = i + 1
        gap_score = (1 - similarity) * (1 / rank_position)
        scores[u] = gap_score
        logger.info(f"📊 [SERP] Rank {rank_position} | Similarity: {similarity:.3f} | Gap Score: {gap_score:.3f}")
        
    sorted_urls = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    priority_urls = sorted_urls[:3]
    
    total_len = sum(len(comp_texts[u]) for u in priority_urls)
    if total_len > 80000:
        logger.warning(f"⚠️ [SERP] Competitor texts too long ({total_len} chars). Trimming to top 1.")
        priority_urls = sorted_urls[:1]
        
    competitor_context = ""
    for u in priority_urls:
        competitor_context += f"--- COMPETITOR: {u} ---\n{comp_texts[u][:20000]}\n\n"
        
    return {
        "lowest_urls": priority_urls,
        "competitor_scores": scores,
        "competitor_context": competitor_context
    }

async def _generate_seo_gap_report(session: aiohttp.ClientSession, my_text: str, competitor_context: str) -> Optional[str]:
    """Generates an actionable SEO gap report based on competitor texts."""
    logger.info("🧠 [AI-SEO] Generating SEO Gap Report...")

    prompt = (
        "You are an Engineer performing a technical gap analysis.\n"
        "Compare my content against these competitors. "
        "Identify exact technical concepts or implementation details I am missing.\n"
        "Output a bulleted 'Gap Report' only.\n\n"
        f"--- MY CONTENT ---\n{my_text[:10000]}\n\n"
        f"--- COMPETITOR CONTENT ---\n{competitor_context}"
    )

    try:
        report = await _gemma_generate(
            session,
            prompt,
            requested_model="gemma-4-26b-a4b-it",
            fallback_keywords=["26b", "27b", "31b"],
            temperature=0.2,
            timeout_seconds=180,
        )
        logger.info(f"\n{'='*60}\n🔍 SEO GAP REPORT:\n{report}\n{'='*60}")
        return report
    except Exception as e:
        logger.error(f"❌ [AI-SEO] Gap Report Exception ({type(e).__name__}): {str(e) or 'No message'}")
    return None


async def _rewrite_for_syndication(_session: aiohttp.ClientSession, markdown_body: str, persona: str = "") -> Optional[str]:
    """
    The Syndicator. Now uses the battle-tested Atomic Tools with Persona.
    """
    # Create a brief for the atomic tool
    is_short = len(markdown_body.split()) < 20
    if is_short:
        logger.info("🧪 [AI-SYNDICATOR] Detected short topic. Forcing content EXPANSION mode.")
        brief = f"RESEARCH and WRITE a complete, deep-dive technical article based on this topic: '{markdown_body}'. Do NOT just repeat the topic. Provide code, data, and visceral narrative."
    else:
        brief = f"Rewrite the following content for syndication. Ensure zero duplicate content and high engagement.\n\nOriginal:\n{markdown_body[:20000]}"
    
    try:
        # We call the atomic tool directly with persona support
        result = await write_the_content_31b(brief, output_format="md", persona=persona)
        
        # Guard against echoes/short completions
        if len(result.split()) < len(markdown_body.split()) + 50:
            logger.warning("⚠️ [AI-SYNDICATOR] Output seems too short (echo detected). Retrying with strict expansion...")
            result = await write_the_content_31b(f"EXPAND THIS TOPIC INTO A 1000 WORD ARTICLE: {markdown_body}", output_format="md", persona=persona)
            
        return result
    except Exception as e:
        logger.error(f"⚠️ [AI-SYNDICATOR] Atomic rewrite failed: {e}")
        return None


async def generate_ai_assets(session: aiohttp.ClientSession, post_data: PostData, state: Dict[str, Any], persona: str = "") -> Tuple[str, List[str], str]:
    """
    Main Orchestrator: Gemma-backed hook, tag, SEO, and syndication generation.
    """
    logger.info("🧠 [AI-ORCHESTRATOR] Commencing AI pipeline execution...")

    # 1. Start the heavy Gemma syndication task first.
    logger.info("🧠 [AI-ORCHESTRATOR] Spawning background Syndicator task (Gemma)...")
    rewrite_task = asyncio.create_task(
        _rewrite_for_syndication(session, post_data.markdown_body, persona=persona)
    )

    # 2. Sequential hook drafts keep model pressure predictable during demos.
    styles: List[str] = [
        "Create a punchy, technical, 'Hacker News' style hook.",
        "Create an educational, 'Senior-to-Junior' mentorship style hook."
    ]

    drafts: List[str] = []
    logger.info("🧠 [AI-ORCHESTRATOR] Processing Hook Drafts sequentially with Gemma...")
    for idx, style in enumerate(styles):
        draft: Optional[str] = await _draft_style(session, post_data.markdown_body, style, draft_id=idx + 1)
        if draft:
            drafts.append(draft)
        await asyncio.sleep(1)

    # SERP Competitor Analysis Injection
    query = state.get("serp_query")
    if not query:
        query = await _generate_search_query(session, post_data.title)
        state["serp_query"] = query
        
    comp_scores = state.get("competitor_scores")
    
    if not comp_scores:
        urls = await _fetch_organic_serp(session, query)
        if urls:
            state["competitor_links"] = urls
            comp_texts = await _extract_competitor_texts(urls)
            gap_data = await _analyze_gaps_via_embeddings(session, post_data.markdown_body, comp_texts)
            state["competitor_scores"] = gap_data["competitor_scores"]
            competitor_context = gap_data["competitor_context"]
            state["competitor_context"] = competitor_context
            
            # Generate and save the SEO Gap Report
            if competitor_context:
                gap_report = await _generate_seo_gap_report(session, post_data.markdown_body, competitor_context)
                if gap_report:
                    state["seo_gap_report"] = gap_report
            # Note: The caller (_phase2) will save `state` if it was modified

    final_hook: str = await _refine_best(session, drafts, post_data=post_data)

    logger.info("🧠 [AI-ORCHESTRATOR] Hook complete. Proceeding to Tag Extraction...")
    dynamic_tags: List[str] = await _generate_dynamic_tags(session, post_data.markdown_body)

    # 3. Await the background Syndication task with a safety timeout (5 mins)
    logger.info("🧠 [AI-ORCHESTRATOR] Waiting for Syndicator task to wrap up (5m timeout)...")
    try:
        syndicated_body = await asyncio.wait_for(rewrite_task, timeout=300)
    except asyncio.TimeoutError:
        logger.error("❌ [AI-ORCHESTRATOR] Syndicator task timed out after 300s!")
        syndicated_body = None
    except Exception as e:
        logger.error(f"❌ [AI-ORCHESTRATOR] Syndicator task failed: {e}")
        syndicated_body = None

    # 4. Final Data Checks
    if not final_hook:
        logger.warning("⚠️ [AI-ORCHESTRATOR] final_hook is empty, using summary fallback.")
        final_hook = (post_data.post_summary or "Check out the latest update.")

    if not dynamic_tags:
        logger.warning("⚠️ [AI-ORCHESTRATOR] dynamic_tags is empty, using config fallback.")
        dynamic_tags = CONFIG.TAGS if CONFIG.TAGS else ["Tech", "Programming"]

    if not syndicated_body:
        logger.warning("⚠️ [AI-ORCHESTRATOR] syndicated_body is empty, triggering Ultimate HTML Fallback.")
        syndicated_body = fallback_teaser(post_data.html_content, final_hook)

    logger.info("✅ [AI-ORCHESTRATOR] Pipeline execution complete.")
    return final_hook, dynamic_tags, str(syndicated_body)

# ==========================================
# 6. INGESTION (The Oracle)
# ==========================================
async def fetch_latest_blogger_post(session: aiohttp.ClientSession, state: Dict[str, Any]) -> PostData:
    logger.info("⏳ Consulting the Blogger Oracle...")
    feed_url: str = f"{CONFIG.BLOGGER_URL}/feeds/posts/default?alt=json"

    async with session.get(feed_url, timeout=timeout) as response:
        if response.status != 200:
            raise FatalError(f"Failed to read Blogger feed. HTTP {response.status}")
        try:
            data = await response.json()
        except Exception as e:
            raise TransientError(f"Blogger response invalid: {e}")

        entries: List[Dict[str, Any]] = data.get('feed', {}).get('entry', [])
        if not entries:
            raise FatalError("No posts found")
        latest_entry: Dict[str, Any] = entries[0]

        title: str = latest_entry.get('title', {}).get('$t', 'Untitled')
        html_content: Optional[str] = latest_entry.get("content", {}).get("$t")
        if not html_content:
            raise FatalError("No content found")

        post_summary: Optional[str] = smart_truncate(html_content)

        canonical_url: str = next((link['href'] for link in latest_entry['link'] if link['rel'] == 'alternate'),
                             CONFIG.BLOGGER_URL)

        # 🚀 OPTIMIZATION: Cache Lexbor Parsing
        is_same_post: bool = (title.strip().lower() == state.get("current_title", ""))

        if is_same_post and "cached_image_url" in state:
            image_url = state["cached_image_url"]
            # Only log if it's an actual URL to prevent spamming None
            if image_url:
                logger.info("⚡ Using cached Lexbor image extraction.")
        else:
            image_url = _extract_blogger_image(LexborHTMLParser(html_content))

        markdown_body: str = markdownify(html_content, heading_style="ATX", strip=[])

        logger.info(f"✅ Fetched: '{title}'")

        return PostData(
            title=title,
            markdown_body=markdown_body,
            canonical_url=canonical_url,
            post_summary=post_summary or "New technical update.",
            html_content=html_content or "",
            image_url=image_url
        )


# ==========================================
# 7. DISTRIBUTION SPOKES (Plugins)
# ==========================================

async def post_to_devto(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "devto"
    if CONFIG.DRY_RUN:
        return PLATFORM, "success"

    logger.info(f"⏳ Forging {PLATFORM} post: {post_data.title}")
    url: str = "https://dev.to/api/articles"
    headers: Dict[str, str] = {"api-key": CONFIG.DEVTO_API_KEY, "Content-Type": "application/json"}

    payload: Dict[str, Any] = {
        "article": {
            "title": post_data.title,
            "body_markdown": (post_data.syndicated_body or post_data.markdown_body),
            "published": True,
            "tags": (post_data.dynamic_tags or CONFIG.TAGS)
        }
    }

    try:
        async for attempt in retrier:
            with attempt:
                async with session.post(url, headers=headers, json=payload, timeout=15) as response:
                    status_code: int = response.status
                    if status_code == 201:
                        logger.info(f"✅ {PLATFORM} live.")
                        return PLATFORM, "success"

                    resp_text: str = await response.text()
                    if status_code in (429, 500, 502, 503, 504):
                        raise TransientError(f"Retryable {status_code}: {resp_text}")
                    else:
                        logger.error(f"❌ {PLATFORM} Fatal {status_code}: {resp_text}")
                        raise FatalError(f"DevTo Bad Request: {resp_text}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"


async def post_to_linkedin(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "linkedin"
    if CONFIG.DRY_RUN:
        return PLATFORM, "success"

    logger.info("⏳ Forging the LinkedIn broadcast...")

    final_text: str = (post_data.ai_hook or post_data.post_summary)

    url: str = "https://api.linkedin.com/v2/ugcPosts"
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {CONFIG.LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    payload: Dict[str, Any] = {
        "author": f"urn:li:person:{CONFIG.LINKEDIN_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": f"⚔️ {post_data.title}\n\n{final_text}"
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    try:
        async for attempt in retrier:
            with attempt:
                async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                    if response.status == 201:
                        logger.info(f"✅ {PLATFORM} live.")
                        return PLATFORM, "success"
                    elif response.status in (429, 500, 502, 503, 504):
                        raise TransientError(f"LinkedIn Rate/Server Limit: {response.status}")
                    else:
                        resp_text = await response.text()
                        raise FatalError(f"LinkedIn Bad Request: {response.status} - {resp_text}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"


async def post_to_bluesky(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "bluesky"
    if CONFIG.DRY_RUN :
        return PLATFORM, "success"

    logger.info("⏳ Forging Bluesky broadcast...")
    final_text: str = (post_data.ai_hook or post_data.post_summary)

    client: AsyncClient = AsyncClient()

    try:
        async for attempt in retrier:
            with attempt:
                try:
                    await client.login(CONFIG.BLUESKY_HANDLE, CONFIG.BLUESKY_APP_PASSWORD)
                    text_content: str = f"⚔️ {post_data.title}\n\n{final_text}"

                    await client.send_post(text=text_content[:300])
                    logger.info(f"✅ {PLATFORM} live.")
                    return PLATFORM, "success"

                except AtProtocolError as e:
                    err_str: str = str(e).lower()
                    if any(x in err_str for x in ["timeout", "500", "502", "503", "504", "429"]):
                        raise TransientError(f"Bluesky Network/Rate Limit: {e}")
                    else:
                        raise FatalError(f"Bluesky Fatal Error: {e}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"


async def post_to_mastodon(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "mastodon"
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    logger.info("⏳ Broadcasting to the Fediverse (Mastodon)...")
    final_text = (post_data.ai_hook or post_data.post_summary)

    try:
        async for attempt in retrier:
            with attempt:
                try:
                    masto = Mastodon(access_token=CONFIG.MASTODON_ACCESS_TOKEN,
                                     api_base_url=CONFIG.MASTODON_INSTANCE_URL)

                    tags = " ".join([f"#{t}" for t in (post_data.dynamic_tags or CONFIG.TAGS)])

                    status_text = (
                        f"⚔️ {post_data.title}\n\n"
                        f"{final_text}\n\n"
                        f"{tags}"
                    )
                    # Sliced exactly at 500 characters to prevent Mastodon API rejection
                    await asyncio.to_thread(masto.status_post, status=status_text[:500], visibility='public')
                    logger.info(f"✅ {PLATFORM} live.")
                    return PLATFORM, "success"

                except (MastodonNetworkError, ConnectionError) as e:
                    raise TransientError(f"Mastodon Network Issue: {e}")
                except MastodonAPIError as e:
                    if "429" in str(e) or "500" in str(e):
                        raise TransientError(f"Mastodon Server/Rate Limit: {e}")
                    raise FatalError(f"Mastodon Fatal API Error: {e}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"


async def post_to_telegram(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "telegram"
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    logger.info("⏳ Broadcasting to Telegram...")

    final_text: str = (post_data.ai_hook or post_data.post_summary or "")

    url: str = f"https://api.telegram.org/bot{CONFIG.TELEGRAM_TOKEN}/sendMessage"
    message: str = f"⚔️ {post_data.title}\n\n{final_text}"

    payload: Dict[str, Any] = {"chat_id": CONFIG.TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": False}

    try:
        async for attempt in retrier:
            with attempt:
                async with session.post(url, json=payload, timeout=10) as response:
                    status_code: int = response.status
                    if status_code == 200:
                        logger.info(f"✅ {PLATFORM} live.")
                        return PLATFORM, "success"

                    resp_text: str = await response.text()
                    if status_code in (429, 500, 502, 503, 504):
                        raise TransientError(f"{PLATFORM} retryable {status_code}: {resp_text}")

                    logger.error(f"❌ {PLATFORM} Fatal {status_code}: {resp_text}")
                    raise FatalError(f"Telegram Bad Request: {resp_text}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"


async def post_to_hashnode(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "hashnode"
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    logger.info("⏳ Forging Hashnode post...")
    url: str = "https://gql.hashnode.com/"
    headers: Dict[str, str] = {"Authorization": CONFIG.HASHNODE_TOKEN, "Content-Type": "application/json"}
    query: str = "mutation PublishPost($input: PublishPostInput!) { publishPost(input: $input) { post { url } } }"

    variables: Dict[str, Any] = {
        "input": {
            "title": post_data.title,
            "contentMarkdown": (post_data.syndicated_body or post_data.markdown_body or ""),
            "publicationId": CONFIG.HASHNODE_PUB_ID
        }
    }

    try:
        async for attempt in retrier:
            with attempt:
                async with session.post(url, headers=headers, json={"query": query, "variables": variables},
                                        timeout=timeout) as response:
                    if response.status in (429, 500, 502, 503, 504):
                        raise TransientError(f"Hashnode Rate/Server Limit: {response.status}")
                    data: Dict[str, Any] = await response.json()
                    if "errors" not in data:
                        logger.info(f"✅ {PLATFORM} live.")
                        return PLATFORM, "success"
                    else:
                        raise FatalError(f"Hashnode GraphQL Error: {data['errors']}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"



async def post_to_nostr(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "nostr"
    if CONFIG.DRY_RUN:
        return PLATFORM, "success"

    logger.info(f"⏳ Broadcasting to Nostr Relays...")

    try:
        # 1. Setup Identity (Using the exact UniFFI bindings)
        keys: Keys = Keys.parse(CONFIG.NOSTR_PRIVATE_ID)
        signer: NostrSigner = NostrSigner.keys(keys)

        # 🚀 2. The Fix: Use ClientBuilder to bypass the constructor crash
        client: Any = ClientBuilder().signer(signer).build()

        # 3. Add Relays (Must be parsed as RelayUrl objects now)
        relays: List[str] = ["wss://nos.lol", "wss://relay.damus.io", "wss://relay.snort.social"]
        for r in relays:
            await client.add_relay(RelayUrl.parse(r))

        await client.connect()

        # 4. Craft the Message
        #no tracking because nostr specifically dont want it
        final_text: str = post_data.syndicated_body or ""
        tags_str: str = " ".join([f"#{t}" for t in (post_data.dynamic_tags or [])])

        content: str = (
            f"⚔️ {post_data.title}\n\n"
            f"{final_text}\n\n"
            f"{tags_str}"
        )

        # 5. Sign and Send Note (No empty arrays allowed here anymore)
        builder = EventBuilder.text_note(content)
        await client.send_event_builder(builder)

        # Cleanup
        await client.disconnect()

        logger.info(f"✅ {PLATFORM} live.")
        return PLATFORM, "success"

    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {type(e).__name__} - {e}")
        return PLATFORM, "failed"


async def post_to_discord(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "discord"
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    logger.info("⏳ Notifying the Discord Council...")

    final_text = (post_data.ai_hook or post_data.post_summary)

    payload = {
        "username": "The Dharma Bot",
        "embeds": [{
            "title": f"⚔️ {post_data.title}",
            "description": final_text,
            "color": 16750848
        }]
    }

    try:
        async for attempt in retrier:
            with attempt:
                async with session.post(CONFIG.DISCORD_WEBHOOK, json=payload, timeout=timeout) as response:
                    if response.status == 204:
                        logger.info(f"✅ {PLATFORM} live.")
                        return PLATFORM, "success"
                    elif response.status in (429, 500, 502, 503, 504):
                        raise TransientError(f"Discord Rate/Server Limit: {response.status}")
                    else:
                        raise FatalError(f"Discord Bad Request: {response.status}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"


async def post_to_paragraph(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "paragraph"
    if CONFIG.DRY_RUN:
        return PLATFORM, "success"

    logger.info(f"⏳ Distributing to Paragraph: {post_data.title}")

    # UPDATED: Correct Public API Endpoint
    url = "https://public.api.paragraph.com/api/v1/posts"

    # UPDATED: Standard Authorization Bearer Token
    headers = {
        "Authorization": f"Bearer {CONFIG.PARAGRAPH_API_KEY}",
        "Content-Type": "application/json"
    }

    # Grab the preferred body content
    body_content : str  = (post_data.syndicated_body or post_data.markdown_body)

    # ARCHITECTURAL NOTE: Paragraph requires 'markdown' and 'title'.
    payload = {
        "title": post_data.title,
        "markdown": body_content,
        "subtitle": post_data.ai_hook,
        "imageUrl": post_data.image_url,
        "sendNewsletter": True,
        "categories": post_data.dynamic_tags or []
    }

    logger.info(f"📤 [PARAGRAPH] Sending payload with keys: {list(payload.keys())}")

    try:
        async for attempt in retrier:
            with attempt:
                # Increased timeout to 30s to handle Arweave-native processing latency.
                async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"✅ {PLATFORM} live.")
                        return PLATFORM, "success"

                    resp_text = await resp.text()
                    if resp.status in (429, 500, 502, 503, 504):
                        raise TransientError(f"Paragraph Retryable {resp.status}: {resp_text}")
                    else:
                        logger.error(f"❌ {PLATFORM} Fatal {resp.status}: {resp_text}")
                        raise FatalError(f"Paragraph API Error: {resp_text}")
    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"

#======================================
#ACCESSIBILITY TEST
#=======================================
async def run_accessibility_audit(url: str) -> Dict[str, Any]:
    """
    Background Task: Deep DOM analysis for accessibility.
    Focuses on 'critical' impact violations.
    """
    logger.info(f"🛡️  Axe-Core: Initiating background audit for {url}...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)

            axe = Axe()
            results = await axe.run(page)
            await browser.close()

            # ✅ FIX: Access the raw JSON dictionary via .response
            raw_data = results.response
            violations = raw_data.get("violations", [])

            # Now we can safely filter dictionaries
            critical_violations = [v for v in violations if v.get("impact") == "critical"]

            summary = []
            for v in critical_violations:
                node_count = len(v.get("nodes", []))
                summary.append(f"{v.get('id')} ({node_count} instances)")

            return {
                "critical_count": len(critical_violations),
                "summary": ", ".join(summary) if summary else "None",
                "success": True
            }
    except Exception as e:
        logger.error(f"❌ Axe Audit Failed: {e}")
        return {"critical_count": 0, "success": False, "error": str(e)}

# ==========================================
# CANONICAL URL LIVENESS CHECK
# ==========================================
async def check_canonical_liveness(session, url):
    """Verifies the canonical URL actually returns HTTP 200 before broadcasting."""
    logger.info(f"🔗 Liveness: Checking {url}...")
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
            if resp.status == 200:
                logger.info(f"✅ Liveness: {url} → HTTP 200 OK")
                return {"success": True, "status": resp.status}
            else:
                logger.error(f"❌ Liveness: {url} → HTTP {resp.status}")
                return {"success": False, "status": resp.status, "error": f"HTTP {resp.status}"}
    except Exception as e:
        logger.error(f"❌ Liveness: Connection failed for {url}: {e}")
        return {"success": False, "status": 0, "error": str(e)}

# ==========================================
# BROKEN IMAGE DETECTION
# ==========================================
async def check_broken_images(session, html_content, canonical_url):
    """Scans HTML for <img> tags and verifies each src returns HTTP 200."""
    logger.info("🖼️ Broken Image Scan: Checking all image sources...")
    parser = LexborHTMLParser(html_content)
    broken = []
    checked = 0

    async def _check_single(image_src: str) -> Tuple[Optional[str], Any]:
        try:
            async with session.head(image_src, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as resp:
                if resp.status != 200:
                    return image_src, resp.status
        except Exception as e:
            return image_src, str(e)
        return None, None

    tasks = []
    for img in parser.css("img"):
        src = img.attributes.get("src")
        if src:
            # Resolve relative URLs
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                from urllib.parse import urljoin
                src = urljoin(canonical_url, src)
            if src.startswith("http"):
                tasks.append(_check_single(src))
                checked += 1

    if not tasks:
        logger.info("🖼️ Broken Image Scan: No images found to check.")
        return {"success": True, "broken_count": 0, "checked": 0, "broken_urls": []}

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            continue
        src, status = result
        if src is not None:
            broken.append({"src": src, "status": status})
            logger.warning(f"  ❌ Broken image: {src} → {status}")

    if broken:
        logger.error(f"🖼️ Broken Image Scan: {len(broken)}/{checked} images broken!")
    else:
        logger.info(f"✅ Broken Image Scan: All {checked} images healthy.")

    return {
        "success": True,
        "broken_count": len(broken),
        "checked": checked,
        "broken_urls": broken
    }

# ==========================================
# W3C HTML VALIDATION (Free — No API Key)
# ==========================================
async def validate_w3c_html(session, url):
    """
    Validates HTML against the W3C Nu Html Checker.
    Endpoint: https://validator.w3.org/nu/?doc=URL&out=json
    100% free, no auth, no API key. Run by the W3C.
    """
    logger.info(f"📝 W3C: Validating HTML for {url}...")
    api_url = "https://validator.w3.org/nu/"
    params = {"doc": url, "out": "json"}

    try:
        async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.error(f"❌ W3C Validator returned HTTP {resp.status}")
                return {"success": False, "error": f"HTTP {resp.status}"}

            data = await resp.json()
            messages = data.get("messages", [])

            errors = [m for m in messages if m.get("type") == "error"]
            warnings = [m for m in messages if m.get("type") in ("warning", "info")]

            error_summary = [f"L{m.get('lastLine', '?')}: {m.get('message', '')[:80]}" for m in errors[:5]]

            logger.info(f"📝 W3C: {len(errors)} errors, {len(warnings)} warnings.")
            if errors:
                for e in error_summary:
                    logger.warning(f"  ⚠️ {e}")

            return {
                "success": True,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "errors": error_summary
            }
    except Exception as e:
        logger.error(f"❌ W3C Validation Failed: {e}")
        return {"success": False, "error": str(e)}

# =========================================

#=========================================
# INDEXING REQUEST
#=========================================
class IndexingEngine:
    """
    High-performance, non-blocking Multi-Search Engine Indexing client.
    Supports Google (OAuth2) and Bing (API Key).
    """

    def __init__(self, google_creds, sc_service, bing_api_key: str, host: str, yandex: str):
        self.google_endpoint = "https://indexing.googleapis.com/v3/urlNotifications:publish"
        self.bing_endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrl?apikey={bing_api_key}"
        self.bing_api_key = bing_api_key
        self.host = host
        self.google_scopes = ["https://www.googleapis.com/auth/indexing"]
        self.yandex_token = yandex
        self.google_creds = google_creds
        self.sc_service = sc_service

    @classmethod
    async def create(cls, google_key_path: str, bing_api_key: str, host: str, yandex: str):
        """Async factory: offloads blocking credential load + service build to a thread."""
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
        return cls(google_creds, sc_service, bing_api_key, host, yandex)

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
                logger.info(f"🔍 Detected Schema: {item['richResultType']} - Status: {item['verdict']}")

            return verdict
        except Exception as e:
            logger.error(f"❌ Inspection Failure: {str(e)}")
            return "ERROR"

    async def _get_google_token(self) -> str:
        if not self.google_creds.valid:
            def _refresh():
                from google.auth.transport.requests import Request as SyncRequest
                self.google_creds.refresh(SyncRequest())
            await asyncio.to_thread(_refresh)
        return self.google_creds.token

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
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

                # Match clean host string (remove https://)
                clean_target = self.host.replace("https://", "")
                host_id = next((h['host_id'] for h in hosts_data['hosts'] if clean_target in h['ascii_host_url']), None)

                if not host_id:
                    logger.error(f"❌ Yandex: Host not found for {self.host}")
                    return None

            # 3. Post to Recrawl Queue
            endpoint = f"https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/recrawl/queue"
            async with session.post(endpoint, headers=headers, json={"url": url}) as r:
                if r.status == 202:
                    logger.info(f"✅ Yandex: Acknowledged {url}")
                    return True
                elif r.status == 429:
                    raise TransientError("Yandex Recrawl Quota/Rate Limit Exceeded")
                else:
                    logger.error(f"❌ Yandex Failure: {r.status} - {await r.text()}")
                    r.raise_for_status()
                    return None

        except Exception as e:
            logger.error(f"💀 Yandex Error: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def notify_google(self, session: aiohttp.ClientSession, url: str):
        """Google Indexing API Vyuha."""
        token = await self._get_google_token()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        payload = {"url": url, "type": "URL_UPDATED"}

        async with session.post(self.google_endpoint, headers=headers, json=payload) as resp:
            if resp.status == 200:
                logger.info(f"✅ Google: Acknowledged {url}")
                return True
            logger.error(f"❌ Google Failure: {resp.status} - {await resp.text()}")
            resp.raise_for_status()
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def notify_bing(self, session: aiohttp.ClientSession, url: str):
        """Bing Webmaster API Vyuha."""
        # Bing uses a simple API Key in the URL params
        headers = {"Content-Type": "application/json; charset=utf-8"}
        payload = {
            "siteUrl": self.host,
            "url": url
        }

        async with session.post(url=self.bing_endpoint, headers=headers, json=payload) as resp:
            if resp.status == 200:
                logger.info(f"✅ Bing: Acknowledged {url}")
                return True
            logger.error(f"❌ Bing Failure: {resp.status} - {await resp.text()}")
            resp.raise_for_status()
            return None

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
                    logger.error(f"💀 {engines[idx]} Indexing Pipeline threw Exception: {type(r).__name__} - {str(r)}")

            # Filter and evaluate
            success: bool = all([not isinstance(r, Exception) and r is True for r in results])
            return "indexing-engine", "success" if success else "partial-fail"

#==========================================
#PAGE SPEED INSIGHTS
#==========================================

async def fetch_single_run(session: aiohttp.ClientSession, url: str, api_key: str, run_id: int) -> Optional[dict]:
       # The limiter automatically spaces out these concurrent tasks

        logger.info(f"⏳ PSI Run {run_id}/3 initiating...")

        # Passing parameters as a dict ensures aiohttp URL-encodes them properly.
        # This completely prevents the 400 Bad Request error.
        params = {
            'url': url,
            'key': api_key,
            'strategy': 'mobile',
            # aiohttp handles lists perfectly for duplicate keys (category=seo&category=performance...)
            'category': ['performance', 'accessibility', 'best-practices', 'seo']
        }

        try:
            async with session.get(
                    'https://www.googleapis.com/pagespeedonline/v5/runPagespeed',
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=90)  # Keep a high timeout for full-spectrum runs
            ) as response:

                if response.status == 200:
                    data: Dict[str, Any] = await response.json()
                    logger.info(f"   ↳ Run {run_id} Success.")
                    lighthouse: Dict[str, Any] = data.get("lighthouseResult") or {}
                    categories: Dict[str, Any] = lighthouse.get("categories") or {}
                    # Return a clean dict of just the scores
                    return {cat: categories.get(cat, {}).get("score", 0) * 100 for cat in
                            ["performance", "accessibility", "best-practices", "seo"]}

                elif response.status == 429:
                    logger.warning(f"   ↳ Run {run_id} Rate Limited (429).")
                    return None
                else:
                    logger.error(f"   ↳ Run {run_id} Error: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"   ↳ Run {run_id} Network Exception: {e}")
            return None




async def post_to_tumblr(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM: str = "tumblr"
    if getattr(CONFIG, "DRY_RUN", False):
        return PLATFORM, "success"

    logger.info("⏳ Broadcasting to Tumblr...")

    body_content = post_data.syndicated_body or post_data.markdown_body
    tags = post_data.dynamic_tags or getattr(CONFIG, "TAGS", [])

    try:
        import pytumblr
        client = pytumblr.TumblrRestClient(
            CONFIG.TUMBLR_CONSUMER_KEY,
            CONFIG.TUMBLR_CONSUMER_SECRET,
            CONFIG.TUMBLR_OAUTH_TOKEN,
            CONFIG.TUMBLR_OAUTH_SECRET
        )

        def _post():
            if post_data.image_url:
                # Use a Photo Post for better dashboard engagement
                caption: str = f"## {post_data.title}\n\n{body_content}"
                return client.create_photo(
                    CONFIG.TUMBLR_BLOG_NAME,
                    state="published",
                    source=post_data.image_url,
                    caption=caption,
                    format="markdown",
                    tags=tags
                )
            else:
                # Fallback to Text Post
                full_body: str = f"{body_content}"
                return client.create_text(
                    CONFIG.TUMBLR_BLOG_NAME,
                    state="published",
                    title=post_data.title,
                    body=full_body,
                    format="markdown",
                    tags=tags
                )

        async for attempt in retrier:
            with attempt:
                resp = await asyncio.to_thread(_post)
                if 'errors' in resp or ('meta' in resp and resp['meta']['status'] >= 400):
                    status = resp.get('meta', {}).get('status', 500)
                    if status in (429, 500, 502, 503, 504):
                        raise TransientError(f"Tumblr Error {status}: {resp}")
                    else:
                        raise FatalError(f"Tumblr Fatal Error: {resp}")
                
                logger.info(f"✅ {PLATFORM} live.")
                return PLATFORM, "success"

    except Exception as e:
        logger.error(f"💀 {PLATFORM} Exception: {e}")
        return PLATFORM, "failed"
    return PLATFORM, "failed"

# ==========================================
# 8. EXECUTION HUB
# ==========================================
PLATFORMS: List[Callable[[aiohttp.ClientSession, PostData], Coroutine[Any, Any, Tuple[str, str]]]] = [
    post_to_devto, post_to_linkedin, post_to_hashnode,
    post_to_discord, post_to_bluesky, post_to_mastodon, 
    post_to_telegram, post_to_nostr, post_to_paragraph, post_to_tumblr
]

async def run_and_persist(session: aiohttp.ClientSession, post_data: PostData, platform_func: Callable[[aiohttp.ClientSession, PostData], Coroutine[Any, Any, Tuple[str, str]]], state: Dict[str, Any]) -> Tuple[str, str]:
    platform_name = platform_func.__name__.replace("post_to_", "")

    try:
        result = await platform_func(session, post_data)
        _, status = result

        state["platforms"][platform_name] = status
        await save_state(state)  # ✅ immediate persistence

        return result

    except Exception as e:
        logger.error(f"{platform_name} crashed: {e}")
        state["platforms"][platform_name] = "failed"
        await save_state(state)
        return platform_name, "failed"


# --- PHASE 1: INGESTION & STATE ---
async def _phase1_ingest_and_sync_state(session: aiohttp.ClientSession, topic: str = "") -> Tuple[Dict[str, Any], PostData, List[Callable]]:
    """Loads state, fetches the newest article, and resets state if content is new."""
    try:
        # 🚀 ADDED: Explicit type hint to prevent IDE type inference errors
        state: dict[str, Any] = await load_state()
    except Exception as e:
        logger.error(f"{e} STATE LOAD FAILED")
        raise

    try:
        if topic:
            logger.info(f"📝 Topic Override Active: {topic[:50]}...")
            # Create a mock PostData from the topic
            post_data = PostData(
                title=topic[:100],
                markdown_body=topic,
                canonical_url=CONFIG.BLOGGER_URL,
                post_summary=topic[:200],
                html_content=f"<p>{topic}</p>",
                image_url=None
            )
        else:
            post_data = await fetch_latest_blogger_post(session, state)
    except FatalError as e:
        logger.error(f"Ingestion Aborted: {e}")
        raise

    is_new_content: bool = False

    if getattr(CONFIG, "CHECK_TITLE_ONLY", False):
        new_title: str = post_data.title.strip().lower()
        if new_title != state.get("current_title"):
            is_new_content = True
            state["current_title"] = new_title
    else:
        new_hash: str = compute_content_hash(post_data)
        if new_hash != state.get("current_hash"):
            is_new_content = True
            state["current_hash"] = new_hash

    if is_new_content or topic:
        logger.info("🔄 New content/Topic override active. Resetting platform states & AI assets.")
        state["platforms"] = {}
        state["cached_image_url"] = post_data.image_url
        state.pop("reason", None)
        state["ai_hook"] = None
        state["dynamic_tags"] = None
        
        # Clear all Quality Gate and SERP caches
        for cache_key in ["psi_scores", "axe_report", "liveness_report", "images_report", "w3c_report", "syndicated_body", "seo_gap_report", "competitor_scores", "competitor_context", "serp_query"]:
            state.pop(cache_key, None)
            
        await save_state(state)

    pending_platforms: List[Callable] = [p for p in PLATFORMS if
                         state["platforms"].get(p.__name__.replace("post_to_", "")) != "success"]



    return state, post_data, pending_platforms



# --- PHASE 2: GATEKEEPER, PSI, AXE, & AI ---
async def _prepare_ai_assets(session: aiohttp.ClientSession, state: Dict[str, Any], post_data: PostData, persona: str = "", force_regenerate: bool = False) -> PostData:
    if force_regenerate or not state.get("ai_hook") or not state.get("dynamic_tags") or not state.get("syndicated_body"):
        final_hook, dynamic_tags, syndicated_body = await generate_ai_assets(session, post_data, state, persona=persona)
        state["ai_hook"] = final_hook
        state["dynamic_tags"] = dynamic_tags
        state["syndicated_body"] = syndicated_body
        await save_state(state)
    else:
        logger.info("🧠 Unified AI assets loaded successfully from state.")
        final_hook = state["ai_hook"]
        dynamic_tags = state["dynamic_tags"]
        syndicated_body = state["syndicated_body"]

    post_data = replace(post_data, ai_hook=final_hook, dynamic_tags=dynamic_tags, syndicated_body=syndicated_body)
    formatted_tags = " ".join([f"#{t}" for t in dynamic_tags])
    
    logger.info("\n" + "=" * 60)
    logger.info("📢 UNIFIED AI ASSET PREVIEW:")
    logger.info("-" * 60)
    logger.info(f"HOOK: {final_hook}")
    logger.info(f"TAGS: {formatted_tags}")
    logger.info("-" * 60)
    logger.info(f"SYNDICATED BODY PREVIEW (First 500 chars):\n{syndicated_body[:500]}...")
    logger.info("-" * 60)
    

    # Save a report file for easy viewing in Content-Only mode
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(script_dir, "latest_content_report.md")
    try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"# GemmaForge Content Report\n\n")
                f.write(f"## Hook\n{final_hook}\n\n")
                f.write(f"## Tags\n{formatted_tags}\n\n")
                f.write(f"## Syndicated Content\n{syndicated_body}\n")
            logger.info(f"💾 Full report saved to: {report_path}")
    except Exception as e:
            logger.error(f"Failed to save report: {e}")


    logger.info("=" * 60 + "\n")

    return post_data

async def _phase2_validate_and_prepare(
    session: aiohttp.ClientSession,
    state: Dict[str, Any],
    post_data: PostData,
    pending_platforms: List[Callable],
    run_quality_checks: bool = True,
    ping_search_engines: bool = True,
    content_only: bool = False,
    persona: str = ""
) -> Union[PostData, bool]:
    """Handles early exits, PageSpeed checks, Axe Accessibility checks, and AI assets."""

    # 1. Gatekeeper
    if not pending_platforms and not content_only:
        logger.info("✅ Content is already synchronized across all social platforms.")
        if ping_search_engines and state["platforms"].get("indexing-engine") != "success":
            logger.info(f"STARTING INDEX REQUEST {post_data.canonical_url}")
            engine = await IndexingEngine.create(
                "service_account_key.json",
                bing_api_key=CONFIG.BING_API,
                host=CONFIG.BLOGGER_URL,
                yandex=CONFIG.YANDEX_CODE
            )
            await engine.notify_all(post_data.canonical_url)
            state["platforms"]["indexing-engine"] = "success"
            await save_state(state)
            # rich results
            await engine.inspect_rich_results(url=post_data.canonical_url)
        elif not ping_search_engines:
            logger.info("Search engine indexing skipped by engine flag.")
        return False  # Signal to stop execution pipeline


    # 2. Bypass Quality Gates if in content_only or checks disabled
    if not run_quality_checks or content_only:
        logger.info("⚡ Quality gates skipped by engine mode.")
        state.pop("reason", None)
        await save_state(state)
        return await _prepare_ai_assets(session, state, post_data, persona=persona, force_regenerate=content_only)

    use_cache: bool = not getattr(CONFIG, "RE_TEST_ON_RETRY", False)

    # 🔥 2. Launch ALL Quality Gates in PARALLEL via asyncio.gather
    psi_cached: bool = use_cache and bool(state.get("psi_scores"))
    axe_cached: bool = use_cache and bool(state.get("axe_report"))
    liveness_cached: bool = use_cache and bool(state.get("liveness_report"))
    images_cached: bool = use_cache and bool(state.get("images_report"))
    w3c_cached: bool = use_cache and bool(state.get("w3c_report"))

    avg_scores: Optional[Dict[str, Any]] = None
    axe_report: Optional[Dict[str, Any]] = None
    liveness: Optional[Dict[str, Any]] = None
    img_report: Optional[Dict[str, Any]] = None
    w3c_report: Optional[Dict[str, Any]] = None

    if psi_cached:
        avg_scores = state["psi_scores"]
        logger.info("⚡ Using cached PSI scores.")
    if axe_cached:
        axe_report = state["axe_report"]
        logger.info("⚡ Using cached Axe-Core report.")
    if liveness_cached:
        liveness = state["liveness_report"]
        logger.info("⚡ Using cached Liveness report.")
    if images_cached:
        img_report = state["images_report"]
        logger.info("⚡ Using cached Broken Images report.")
    if w3c_cached:
        w3c_report = state["w3c_report"]
        logger.info("⚡ Using cached W3C HTML report.")

    # Build parallel tasks for anything not cached
    parallel_tasks = {}
    if not psi_cached:
        parallel_tasks["psi"] = fetch_single_run(session, post_data.canonical_url, api_key=CONFIG.PSI_API, run_id=1)
    if not axe_cached:
        parallel_tasks["axe"] = run_accessibility_audit(post_data.canonical_url)
    if not liveness_cached:
        parallel_tasks["liveness"] = check_canonical_liveness(session, post_data.canonical_url)
    if not images_cached:
        parallel_tasks["images"] = check_broken_images(session, post_data.html_content, post_data.canonical_url)
    if not w3c_cached:
        parallel_tasks["w3c"] = validate_w3c_html(session, post_data.canonical_url)

    logger.info(f"🚀 Firing {len(parallel_tasks)} quality gate(s) in parallel: {list(parallel_tasks.keys())}")
    results = await asyncio.gather(*parallel_tasks.values(), return_exceptions=True)
    result_map = dict(zip(parallel_tasks.keys(), results))

    if "psi" in result_map:
        avg_scores = result_map["psi"] if not isinstance(result_map["psi"], Exception) else None
        if avg_scores and not any(val is None for val in avg_scores.values()):
            state["psi_scores"] = avg_scores
            await save_state(state)
    if "axe" in result_map:
        axe_report = result_map["axe"] if not isinstance(result_map["axe"], Exception) else None
        if axe_report and axe_report.get("success"):
            state["axe_report"] = axe_report
            await save_state(state)
            
    if "liveness" in result_map:
        liveness = result_map["liveness"] if not isinstance(liveness, Exception) else None
        if liveness and liveness.get("success"):
            state["liveness_report"] = liveness
            await save_state(state)

    if "images" in result_map:
        img_report = result_map["images"] if not isinstance(result_map["images"], Exception) else None
        if img_report and img_report.get("success"):
            state["images_report"] = img_report
            await save_state(state)

    if "w3c" in result_map:
        w3c_report = result_map["w3c"] if not isinstance(result_map["w3c"], Exception) else None
        if w3c_report and w3c_report.get("success"):
            state["w3c_report"] = w3c_report
            await save_state(state)

    # ── Gate 1: Canonical URL Liveness (HARD GATE) ──
    if isinstance(liveness, Exception) or not isinstance(liveness, dict) or not liveness.get("success"):
        failure_reason: str = f"CANONICAL URL DOWN: {post_data.canonical_url} is unreachable"
        logger.error(f"🛑 {failure_reason}. Aborting broadcast — no point distributing a dead link.")
        state["reason"] = failure_reason
        await save_state(state)
        return False

    # ── Gate 2: PSI Scores (HARD GATE) ──
    if not psi_cached and not avg_scores:
        pass  # avg_scores not set yet if not cached
    if not avg_scores or not isinstance(avg_scores, dict) or any(val is None for val in avg_scores.values()):
        logger.error("🛑 PSI could not verify all metrics. Aborting to be safe.")
        return False

    logger.info(
        f"📊 AVG SCORES: Perf({avg_scores['performance']:.1f}), Access({avg_scores['accessibility']:.1f}), BestP({avg_scores['best-practices']:.1f}), SEO({avg_scores['seo']:.1f})")

    failed_metrics: List[str] = [f"{c[:4].upper()}({avg_scores[c]:.1f}<{t})" for c, t in CONFIG.PSI_THRESHOLDS.items() if
                      avg_scores[c] < t]
    if failed_metrics:
        failure_reason: str = f"PSI LOW: {', '.join(failed_metrics)}"
        logger.warning(f"🛑 Thresholds failed: {failure_reason}. Aborting broadcast.")
        state["reason"] = failure_reason
        await save_state(state)
        return False

    # ── Gate 3: Axe-Core Accessibility (HARD GATE) ──
    if isinstance(axe_report, dict) and axe_report.get("success"):
        critical_errors: int = axe_report.get("critical_count", 0)
        if critical_errors > 0:
            failure_reason: str = f"AXE CRITICAL ERRORS: {critical_errors} found | {axe_report.get('summary')}"
            logger.error(f"🛑 {failure_reason}. Aborting broadcast.")
            state["reason"] = failure_reason
            await save_state(state)
            return False
        else:
            logger.info("✅ Axe-Core: 0 Critical violations found. DOM is clean.")
    else:
        error_msg = axe_report.get('error') if axe_report else 'Unknown Error'
        logger.warning(f"⚠️ Axe-Core audit crashed ({error_msg}). Proceeding on PSI metrics alone.")

    # ── Gate 4: Broken Images (SOFT GATE — warn only) ──
    if isinstance(img_report, dict) and img_report.get("success"):
        if img_report.get("broken_count", 0) > 0:
            logger.warning(f"⚠️ {img_report['broken_count']} broken image(s) detected. Proceeding but fix these!")
    else:
        logger.warning("⚠️ Broken image check failed. Proceeding anyway.")

    # ── Gate 5: W3C HTML Validation (SOFT GATE — warn only) ──
    if isinstance(w3c_report, dict) and w3c_report.get("success"):
        if w3c_report.get("error_count", 0) > 0:
            logger.warning(f"⚠️ W3C: {w3c_report['error_count']} HTML errors found. Not blocking (Blogger HTML is messy).")
    else:
        logger.warning("⚠️ W3C validation failed. Proceeding anyway.")

    logger.info("✅ All Quality Gates passed! Proceeding to broadcast.")
    state.pop("reason", None)
    await save_state(state)
    return await _prepare_ai_assets(session, state, post_data, persona=persona, force_regenerate=content_only)


# --- PHASE 3: EXECUTION & REPORTING ---
async def _phase3_execute_and_report(
    session: aiohttp.ClientSession,
    state: Dict[str, Any],
    post_data: PostData,
    pending_platforms: List[Callable],
    ping_search_engines: bool = True,
    syndicate_content: bool = True
) -> None:
    """Fires all pending social APIs concurrently and prints the final report."""
    tasks = [run_and_persist(session, post_data, pf, state) for pf in pending_platforms] if syndicate_content else []

    if not syndicate_content:
        logger.info("Syndication skipped by engine flag.")

    if ping_search_engines and state["platforms"].get("indexing-engine") != "success":
        logger.info(f"STARTING INDEX REQUEST {post_data.canonical_url}")
        engine = await IndexingEngine.create("service_account_key.json", bing_api_key=CONFIG.BING_API,
                                              host=CONFIG.BLOGGER_URL, yandex=CONFIG.YANDEX_CODE)
        tasks.append(engine.notify_all(post_data.canonical_url))
    elif not ping_search_engines:
        logger.info("Search engine indexing skipped by engine flag.")

    if not tasks:
        logger.info("No external writes requested. Distribution Complete.")
        return

    logger.info(f"⚙️ Broadcasting to {len(tasks)} targets concurrently...")
    results = await asyncio.gather(*tasks)

    logger.info("\n" + "=" * 40 + "\n📊 EXECUTION REPORT\n" + "=" * 40)
    for result in results:
        platform_name, status = result
        marker = "✅" if status == "success" else "❌"
        logger.info(f"{marker} {platform_name.upper():<15} : {status.upper()}")

        if platform_name == "indexing-engine" and status == "success":
            state["platforms"]["indexing-engine"] = "success"
            await save_state(state)

    logger.info("=" * 40 + "\n🏁 Distribution Complete.")


# --- MAIN ORCHESTRATOR ---
async def main(
    run_quality_checks: bool = True,
    ping_search_engines: bool = True,
    syndicate_content: bool = True,
    content_only: bool = False,
    topic: str = "",
    persona: str = ""
):
    try:
        logger.info("🔥 Igniting the Distribution Engine...")
        logger.info(
            f"Mode flags | quality_checks={run_quality_checks} "
            f"indexing={ping_search_engines} syndication={syndicate_content} content_only={content_only}"
        )
        # Removed the call to fetch_open_pagerank and its print statement
        if CONFIG.DRY_RUN:
            logger.info("⚠️ DRY RUN MODE ACTIVE - No external API writes will occur.")

        resolver = aiohttp.ThreadedResolver()
        connector = aiohttp.TCPConnector(resolver=resolver)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, cookie_jar=DummyCookieJar()) as session:

            # Step 1
            state, post_data, pending_platforms = await _phase1_ingest_and_sync_state(session, topic=topic)

        

            # Step 2
            post_data_or_false: Union[PostData, bool] = await _phase2_validate_and_prepare(
                session,
                state,
                post_data,
                pending_platforms,
                run_quality_checks=run_quality_checks,
                ping_search_engines=ping_search_engines,
                content_only=content_only,
                persona=persona
            )
            if post_data_or_false is False:
                return  # Pipeline aborted intentionally (Gatekeeper or PSI)
            
            if isinstance(post_data_or_false, PostData):
                post_data = post_data_or_false
            else:
                return # Should not happen based on logic but for types

            if content_only:
                logger.info("✅ Content-Only pipeline complete. No posts were made.")
                return

            # Step 3
            await _phase3_execute_and_report(
                session,
                state,
                post_data,
                pending_platforms,
                ping_search_engines=ping_search_engines,
                syndicate_content=syndicate_content,
            )

    except Exception as e:
        logger.error(f"{e} ERROR IN MAIN")
        raise

async def run_with_retries(
    run_quality_checks: bool = True,
    ping_search_engines: bool = True,
    syndicate_content: bool = True,
    content_only: bool = False,
    topic: str = ""
):
    try:
        log_listener.start()
    except RuntimeError:
        pass
    for attempt in range(3):
        try:
            await main(
                run_quality_checks=run_quality_checks,
                ping_search_engines=ping_search_engines,
                syndicate_content=syndicate_content,
                content_only=content_only,
                topic=topic,

            )
            return  # success → stop retrying
        except Exception as e:
            logger.error(f"Run failed (attempt {attempt+1}): {e}")
            await asyncio.sleep(120)
    logger.error("All retries failed")

async def run_content_only(topic: str = "", persona: str = "") -> None:
    try:
        log_listener.start()
    except RuntimeError:
        pass
    await main(
        run_quality_checks=False,
        ping_search_engines=False,
        syndicate_content=False,
        content_only=True,
        topic=topic,
        persona=persona
    )

async def edit_content(instruction: str) -> bool:
    """Edits the latest generated content using the provided instruction and model."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(script_dir, "latest_content_report.md")
        
        if not os.path.exists(report_path):
            logger.error("❌ No content found to edit.")
            return False
            
        with open(report_path, "r", encoding="utf-8") as f:
            current_content = f.read()
            
        # Use Atomic Tool logic for editing
        brief = f"""TASK: Execute string mutation on {current_content} based on {instruction}.

FORMAT ENFORCEMENT:
Return the mutated text in its EXACT original markup format (Markdown/HTML).
DO NOT add conversational text.
DO NOT wrap in formatting blocks.
Output ONLY the final mutated markup.
"""
        
        logger.info(f"🧠 [AI-EDITOR] Sending standardized edit request via Atomic Tools...")
        
        try:
            edited_content = await write_the_content_31b(brief, output_format="md")
            
            if edited_content:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(edited_content)
                logger.info("✅ Edit successful and saved.")
                return True
        except Exception as e:
            logger.error(f"❌ Atomic Edit failed: {e}")
            return False
            
        return False
            
    except Exception as e:
        logger.error(f"❌ Edit Exception: {e}")
        return False

