import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class PostData:
    title: str
    markdown_body: str
    canonical_url: str
    post_summary: str
    html_content: str
    image_url: Optional[str] = None
    ai_hook: Optional[str] = None
    dynamic_tags: Optional[List[str]] = None
    syndicated_body: Optional[str] = None


@dataclass(frozen=True)
class PublisherConfig:
    # Intelligence & Search (Updated to Google AI Studio)
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    SERP_API_KEY: str = os.getenv("SERP_API_KEY", "")
    PSI_API: str = os.getenv("PSI_API", "")
    BLOGGER_URL: str = os.getenv("BLOGGER_URL", "")

    # Gemma Model Names (Google AI Studio - Verified Gemma 4)
    GEMMA_2B_MODEL: str = os.getenv("GEMMA_2B_MODEL", "gemma-4-26b-a4b-it")
    GEMMA_4B_MODEL: str = os.getenv("GEMMA_4B_MODEL", "gemma-4-26b-a4b-it")
    GEMMA_26B_MODEL: str = os.getenv("GEMMA_26B_MODEL", "gemma-4-26b-a4b-it")
    GEMMA_31B_MODEL: str = os.getenv("GEMMA_31B_MODEL", "gemma-4-31b-it")

    # Platform Keys
    DEVTO_API_KEY: str = os.getenv("DEVTO_API_KEY", "")
    HASHNODE_TOKEN: str = os.getenv("HASHNODE_TOKEN", "")
    HASHNODE_PUB_ID: str = os.getenv("HASHNODE_PUB_ID", "")
    DISCORD_WEBHOOK: str = os.getenv("DISCORD_WEBHOOK", "")
    LINKEDIN_ACCESS_TOKEN: str = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    LINKEDIN_PERSON_ID: str = os.getenv("LINKEDIN_PERSON_ID", "")
    BLUESKY_HANDLE: str = os.getenv("BLUESKY_HANDLE", "")
    BLUESKY_APP_PASSWORD: str = os.getenv("BLUESKY_APP_PASSWORD", "")
    MASTODON_ACCESS_TOKEN: str = os.getenv("MASTODON_ACCESS_TOKEN", "")
    MASTODON_INSTANCE_URL: str = os.getenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    NOSTR_PRIVATE_ID: str = os.getenv("NOSTR_PRIVATE_ID", "")
    PARAGRAPH_API_KEY: str = os.getenv("PARAGRAPH_API_KEY", "")
    TUMBLR_CONSUMER_KEY: str = os.getenv("TUMBLR_CONSUMER_KEY", "")
    TUMBLR_CONSUMER_SECRET: str = os.getenv("TUMBLR_CONSUMER_SECRET", "")
    TUMBLR_OAUTH_TOKEN: str = os.getenv("TUMBLR_OAUTH_TOKEN", "")
    TUMBLR_OAUTH_SECRET: str = os.getenv("TUMBLR_OAUTH_SECRET", "")
    TUMBLR_BLOG_NAME: str = os.getenv("TUMBLR_BLOG_NAME", "")
    BING_API: str = os.getenv("BING_API", "")
    YANDEX_CODE: str = os.getenv("YANDEX_CODE", "")

    DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
    TAGS: List[str] = field(default_factory=lambda: ['programming', 'tech'])


CONFIG = PublisherConfig()


class TransientError(Exception):
    pass


class FatalError(Exception):
    pass