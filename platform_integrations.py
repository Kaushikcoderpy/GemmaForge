import asyncio
import urllib.parse
from typing import Tuple
import aiohttp
from atproto import AsyncClient, models
from atproto.exceptions import AtProtocolError
from mastodon import Mastodon, MastodonNetworkError, MastodonAPIError
from nostr_sdk import Keys, RelayUrl, EventBuilder, NostrSigner, ClientBuilder

from configuration_module import CONFIG, PostData, TransientError, FatalError
from logging_module import get_logger

def build_utm_url(base_url: str, platform: str) -> str:
    params = {"utm_source": platform, "utm_medium": "social", "utm_campaign": "gemmaforge"}
    return f"{base_url}?{urllib.parse.urlencode(params)}"

async def post_to_devto(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "devto"
    logger = await get_logger()
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Forging post...")
    url = "https://dev.to/api/articles"
    headers = {"api-key": CONFIG.DEVTO_API_KEY, "Content-Type": "application/json"}
    payload = {
        "article": {
            "title": post_data.title,
            "body_markdown": post_data.syndicated_body or post_data.markdown_body,
            "published": True,
            "tags": post_data.dynamic_tags or CONFIG.TAGS,
            "canonical_url": post_data.canonical_url
        }
    }

    async with session.post(url, headers=headers, json=payload) as response:
        if response.status == 201:
            return PLATFORM, "success"
        resp_text = await response.text()
        if response.status in (429, 500, 502, 503, 504):
            raise TransientError(f"{PLATFORM} Server Limit: {resp_text}")
        raise FatalError(f"{PLATFORM} Bad Request: {resp_text}")

async def post_to_linkedin(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "linkedin"
    logger = await get_logger()
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Forging broadcast...")
    tracked_url = build_utm_url(post_data.canonical_url, PLATFORM)
    final_text = post_data.ai_hook or post_data.post_summary

    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {CONFIG.LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "author": f"urn:li:person:{CONFIG.LINKEDIN_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": f"⚔️ {post_data.title}\n\n{final_text}\n\nRead the full breakdown: {tracked_url}"},
                "shareMediaCategory": "ARTICLE",
                "media": [{"status": "READY", "originalUrl": tracked_url, "title": {"text": post_data.title}}]
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    async with session.post(url, headers=headers, json=payload) as response:
        if response.status == 201:
            return PLATFORM, "success"
        if response.status in (429, 500, 502, 503, 504):
            raise TransientError(f"{PLATFORM} Server Limit: {response.status}")
        raise FatalError(f"{PLATFORM} Bad Request: {response.status} - {await response.text()}")

async def post_to_bluesky(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "bluesky"
    logger = await get_logger()
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Forging broadcast...")
    tracked_url = build_utm_url(post_data.canonical_url, PLATFORM)
    final_text = post_data.ai_hook or post_data.post_summary
    client = AsyncClient()

    try:
        await client.login(CONFIG.BLUESKY_HANDLE, CONFIG.BLUESKY_APP_PASSWORD)
        text_content = f"⚔️ {post_data.title}\n\n{final_text}"
        embed_external = models.AppBskyEmbedExternal.Main(
            external=models.AppBskyEmbedExternal.External(
                uri=tracked_url, title=post_data.title, description=final_text[:200]
            )
        )
        await client.send_post(text=text_content[:300], embed=embed_external)
        return PLATFORM, "success"
    except AtProtocolError as e:
        if any(x in str(e).lower() for x in ["timeout", "500", "502", "503", "504", "429"]):
            raise TransientError(f"{PLATFORM} Network Issue: {e}")
        raise FatalError(f"{PLATFORM} Fatal Error: {e}")

async def post_to_mastodon(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "mastodon"
    logger = await get_logger()
    if CONFIG.DRY_RUN: return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Broadcasting to Fediverse...")
    tracked_url = build_utm_url(post_data.canonical_url, PLATFORM)
    final_text = post_data.ai_hook or post_data.post_summary

    try:
        masto = Mastodon(access_token=CONFIG.MASTODON_ACCESS_TOKEN, api_base_url=CONFIG.MASTODON_INSTANCE_URL)
        tags = " ".join([f"#{t}" for t in (post_data.dynamic_tags or CONFIG.TAGS)])
        status_text = f"⚔️ {post_data.title}\n\n{final_text}\n\nRead more: {tracked_url}\n\n{tags}"
        
        await asyncio.to_thread(masto.status_post, status=status_text[:500], visibility='public')
        return PLATFORM, "success"
    except (MastodonNetworkError, ConnectionError) as e:
        raise TransientError(f"{PLATFORM} Network Issue: {e}")
    except MastodonAPIError as e:
        raise FatalError(f"{PLATFORM} Fatal API Error: {e}")

async def post_to_hashnode(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "hashnode"
    logger = await get_logger()
    if getattr(CONFIG, "DRY_RUN", False): return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Forging post...")
    url = "https://gql.hashnode.com/"
    headers = {"Authorization": CONFIG.HASHNODE_TOKEN, "Content-Type": "application/json"}
    query = "mutation PublishPost($input: PublishPostInput!) { publishPost(input: $input) { post { url } } }"
    
    variables = {
        "input": {
            "title": post_data.title,
            "contentMarkdown": post_data.syndicated_body or post_data.markdown_body or "",
            "publicationId": CONFIG.HASHNODE_PUB_ID,
            "originalArticleURL": post_data.canonical_url
        }
    }

    async with session.post(url, headers=headers, json={"query": query, "variables": variables}) as response:
        if response.status in (429, 500, 502, 503, 504):
            raise TransientError(f"{PLATFORM} Server Limit: {response.status}")
        data = await response.json()
        if "errors" not in data:
            return PLATFORM, "success"
        raise FatalError(f"{PLATFORM} GraphQL Error: {data['errors']}")

async def post_to_telegram(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "telegram"
    logger = await get_logger()
    if getattr(CONFIG, "DRY_RUN", False): return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Broadcasting...")
    tracked_url = build_utm_url(post_data.canonical_url, PLATFORM)
    final_text = post_data.ai_hook or post_data.post_summary or ""
    
    url = f"https://api.telegram.org/bot{CONFIG.TELEGRAM_TOKEN}/sendMessage"
    message = f"⚔️ {post_data.title}\n\n{final_text}\n\n👉 {tracked_url}"
    payload = {"chat_id": CONFIG.TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": False}

    async with session.post(url, json=payload) as response:
        if response.status == 200:
            return PLATFORM, "success"
        resp_text = await response.text()
        if response.status in (429, 500, 502, 503, 504):
            raise TransientError(f"{PLATFORM} Server Limit: {resp_text}")
        raise FatalError(f"{PLATFORM} Bad Request: {resp_text}")

async def post_to_discord(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "discord"
    logger = await get_logger()
    if getattr(CONFIG, "DRY_RUN", False): return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Notifying council...")
    tracked_url = build_utm_url(post_data.canonical_url, PLATFORM)
    final_text = post_data.ai_hook or post_data.post_summary

    payload = {
        "username": "The Dharma Bot",
        "embeds": [{
            "title": f"⚔️ {post_data.title}",
            "description": final_text,
            "url": tracked_url,
            "color": 16750848
        }]
    }

    async with session.post(CONFIG.DISCORD_WEBHOOK, json=payload) as response:
        if response.status == 204:
            return PLATFORM, "success"
        if response.status in (429, 500, 502, 503, 504):
            raise TransientError(f"{PLATFORM} Server Limit: {response.status}")
        raise FatalError(f"{PLATFORM} Bad Request: {response.status}")

async def post_to_paragraph(session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "paragraph"
    logger = await get_logger()
    if getattr(CONFIG, "DRY_RUN", False): return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Distributing...")
    url = "https://public.api.paragraph.com/api/v1/posts"
    headers = {
        "Authorization": f"Bearer {CONFIG.PARAGRAPH_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "title": post_data.title,
        "markdown": post_data.syndicated_body or post_data.markdown_body,
        "subtitle": post_data.ai_hook,
        "imageUrl": post_data.image_url,
        "sendNewsletter": True,
        "categories": post_data.dynamic_tags or []
    }

    async with session.post(url, headers=headers, json=payload) as response:
        if response.status in (200, 201):
            return PLATFORM, "success"
        resp_text = await response.text()
        if response.status in (429, 500, 502, 503, 504):
            raise TransientError(f"{PLATFORM} Server Limit: {resp_text}")
        raise FatalError(f"{PLATFORM} API Error: {resp_text}")

async def post_to_nostr(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "nostr"
    logger = await get_logger()
    if getattr(CONFIG, "DRY_RUN", False): return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Broadcasting to Relays...")
    try:
        keys = Keys.parse(CONFIG.NOSTR_PRIVATE_ID)
        signer = NostrSigner.keys(keys)
        client = ClientBuilder().signer(signer).build()

        relays = ["wss://nos.lol", "wss://relay.damus.io", "wss://relay.snort.social"]
        for r in relays:
            await client.add_relay(RelayUrl.parse(r))

        await client.connect()

        final_text = post_data.syndicated_body or ""
        tags_str = " ".join([f"#{t}" for t in (post_data.dynamic_tags or [])])
        content = (
            f"⚔️ {post_data.title}\n\n"
            f"{final_text}\n\n"
            f"🔗 Full breakdown: {post_data.canonical_url}\n\n"
            f"{tags_str}"
        )

        builder = EventBuilder.text_note(content)
        await client.send_event_builder(builder)
        await client.disconnect()
        return PLATFORM, "success"
    except Exception as e:
        raise FatalError(f"{PLATFORM} Client Error: {e}")

async def post_to_tumblr(_session: aiohttp.ClientSession, post_data: PostData) -> Tuple[str, str]:
    PLATFORM = "tumblr"
    logger = await get_logger()
    if getattr(CONFIG, "DRY_RUN", False): return PLATFORM, "success"

    await logger.info(f"[{PLATFORM}] Broadcasting...")
    tracked_url = build_utm_url(post_data.canonical_url, PLATFORM)
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
                caption = f"## {post_data.title}\n\n{body_content}\n\n---\n**[Read the full technical breakdown on my blog]({tracked_url})**"
                return client.create_photo(
                    CONFIG.TUMBLR_BLOG_NAME,
                    state="published",
                    source=post_data.image_url,
                    caption=caption,
                    format="markdown",
                    tags=tags
                )
            else:
                full_body = f"{body_content}\n\n---\n**[Read the full technical breakdown on my blog]({tracked_url})**"
                return client.create_text(
                    CONFIG.TUMBLR_BLOG_NAME,
                    state="published",
                    title=post_data.title,
                    body=full_body,
                    format="markdown",
                    tags=tags
                )

        resp = await asyncio.to_thread(_post)
        if 'errors' in resp or ('meta' in resp and resp['meta']['status'] >= 400):
            status = resp.get('meta', {}).get('status', 500)
            if status in (429, 500, 502, 503, 504):
                raise TransientError(f"{PLATFORM} Server Limit: {resp}")
            raise FatalError(f"{PLATFORM} API Error: {resp}")
        
        return PLATFORM, "success"
    except TransientError:
        raise
    except FatalError:
        raise
    except Exception as e:
        raise FatalError(f"{PLATFORM} Execution Exception: {e}")
