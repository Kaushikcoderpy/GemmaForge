import asyncio
import aiohttp
import logging
from typing import List, Dict, Any, Callable, Coroutine, Tuple

from state_schema import save_state
from configuration_module import CONFIG, PostData
from indexer import IndexingEngine
from platform_integrations import (
    post_to_devto, post_to_linkedin, post_to_bluesky, post_to_mastodon,
    post_to_hashnode, post_to_telegram, post_to_discord, post_to_paragraph,
    post_to_nostr, post_to_tumblr
)


logger = logging.getLogger(__name__)


async def run_and_persist(session: aiohttp.ClientSession, post_data: PostData, platform_func: Callable[..., Coroutine[Any, Any, Tuple[str, str]]], state: Dict[str, Any], name_override: str = None) -> Tuple[str, str]:
    # Use name_override if provided, otherwise derive from function name
    platform_name = name_override if name_override else platform_func.__name__.replace("post_to_", "")

    try:
        result = await platform_func(session, post_data)
        _, status = result

        state["platforms"][platform_name] = status
        await save_state(state)  # Persist state after each platform attempt

        return result

    except Exception as e:
        logger.error(f"{platform_name} crashed: {e}")
        state["platforms"][platform_name] = "failed"
        await save_state(state)
        return platform_name, "failed"


# This list should contain the actual platform functions.
# The user needs to ensure these functions are defined or imported into this file.
# For example, if `distribute.py` was split, these would come from a `platforms.py` module.
PLATFORMS: List[Callable[[aiohttp.ClientSession, PostData], Coroutine[Any, Any, Tuple[str, str]]]] = [
    post_to_devto, post_to_linkedin, post_to_bluesky, post_to_mastodon,
    post_to_hashnode, post_to_telegram, post_to_discord, post_to_paragraph,
    post_to_nostr, post_to_tumblr
]


async def fan_out_pipeline(session: aiohttp.ClientSession, post_data: PostData, state: Dict[str, Any]):
    """
    Orchestrates the concurrent fan-out to various platforms and indexing engines.
    Yields SSE-compatible updates as dictionaries.
    """
    # Filter platforms that haven't been successfully posted to yet
    pending_platforms: List[Callable] = [
        p for p in PLATFORMS
        if state["platforms"].get(p.__name__.replace("post_to_", "")) != "success"
    ]

    tasks = [run_and_persist(session, post_data, pf, state) for pf in pending_platforms]

    # Add indexing engine tasks if not already successful
    if state["platforms"].get("indexing-engine") != "success":
        logger.info(f"STARTING INDEX REQUEST {post_data.canonical_url}")
        # IndexingEngine.create needs CONFIG.BING_API, CONFIG.BLOGGER_URL, CONFIG.YANDEX_CODE
        # These are assumed to be available via CONFIG import.
        indexing_engine_instance = await IndexingEngine.create("service_account_key.json", bing_api_key=CONFIG.BING_API,
                                                                host=CONFIG.BLOGGER_URL, yandex_token=CONFIG.YANDEX_CODE)
        tasks.append(run_and_persist(session, post_data, indexing_engine_instance.notify_all, state, name_override="indexing-engine"))

    logger.info(f"⚙️ Broadcasting to {len(tasks)} targets concurrently...")
    results = await asyncio.gather(*tasks)

    for result in results:
        platform_name, status = result
        yield {"event": "broadcast_update", "message": f"{platform_name.upper()}: {status.upper()}", "data": {"platform": platform_name, "status": status}}

    yield {"event": "broadcast_complete", "message": "Distribution Complete."}