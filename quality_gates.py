import asyncio
import aiohttp
from typing import Dict, Any, Optional, Tuple
from selectolax.lexbor import LexborHTMLParser
from playwright.async_api import async_playwright
from axe_playwright_python.async_playwright import Axe

from config import CONFIG
from logger import get_logger

async def fetch_single_run(session: aiohttp.ClientSession, url: str, api_key: str, run_id: int) -> Optional[Dict[str, float]]:
    logger = await get_logger()
    await logger.info(f"[PSI] Run {run_id}/3 initiating for {url}...")

    params = {
        'url': url,
        'key': api_key,
        'strategy': 'mobile',
        'category': ['performance', 'accessibility', 'best-practices', 'seo']
    }

    try:
        async with session.get(
            'https://www.googleapis.com/pagespeedonline/v5/runPagespeed',
            params=params,
            timeout=aiohttp.ClientTimeout(total=90)
        ) as response:
            if response.status == 200:
                data = await response.json()
                lighthouse = data.get("lighthouseResult", {})
                categories = lighthouse.get("categories", {})
                await logger.info(f"[PSI] Run {run_id} Success.")
                return {cat: categories.get(cat, {}).get("score", 0) * 100 for cat in ["performance", "accessibility", "best-practices", "seo"]}
            
            await logger.warning(f"[PSI] Failed: HTTP {response.status}")
            return None
    except Exception as e:
        await logger.error(f"[PSI] Network Exception: {e}")
        return None

async def run_accessibility_audit(url: str) -> Dict[str, Any]:
    """Background Task: Deep DOM analysis for critical accessibility violations."""
    logger = await get_logger()
    await logger.info(f"[AXE] Initiating background audit for {url}...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)

            axe = Axe()
            results = await axe.run(page)
            await browser.close()

            raw_data = results.response
            violations = raw_data.get("violations", [])
            critical_violations = [v for v in violations if v.get("impact") == "critical"]

            summary = [f"{v.get('id')} ({len(v.get('nodes', []))} instances)" for v in critical_violations]
            
            return {
                "critical_count": len(critical_violations),
                "summary": ", ".join(summary) if summary else "None",
                "success": True
            }
    except Exception as e:
        await logger.error(f"[AXE] Audit Failed: {e}")
        return {"critical_count": 0, "success": False, "error": str(e)}

async def check_canonical_liveness(session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
    logger = await get_logger()
    await logger.info(f"[LIVENESS] Verifying {url}...")
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
            if resp.status == 200:
                return {"success": True, "status": resp.status}
            await logger.error(f"[LIVENESS] Failed: HTTP {resp.status}")
            return {"success": False, "status": resp.status, "error": f"HTTP {resp.status}"}
    except Exception as e:
        await logger.error(f"[LIVENESS] Connection failed: {e}")
        return {"success": False, "status": 0, "error": str(e)}

async def check_broken_images(session: aiohttp.ClientSession, html_content: str, canonical_url: str) -> Dict[str, Any]:
    logger = await get_logger()
    await logger.info("[IMAGES] Scanning DOM for 404 image sources...")
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
            if src.startswith("//"): src = "https:" + src
            elif src.startswith("/"): 
                from urllib.parse import urljoin
                src = urljoin(canonical_url, src)
            if src.startswith("http"):
                tasks.append(_check_single(src))
                checked += 1

    if not tasks:
        return {"success": True, "broken_count": 0, "checked": 0, "broken_urls": []}

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception): continue
        src, status = result
        if src is not None:
            broken.append({"src": src, "status": status})

    if broken:
        await logger.error(f"[IMAGES] {len(broken)}/{checked} images broken!")
    return {"success": True, "broken_count": len(broken), "checked": checked, "broken_urls": broken}

async def validate_w3c_html(session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
    """W3C Nu Html Checker integration."""
    logger = await get_logger()
    await logger.info(f"[W3C] Validating HTML structure for {url}...")
    api_url = "https://validator.w3.org/nu/"
    params = {"doc": url, "out": "json"}

    try:
        async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"HTTP {resp.status}"}
            
            data = await resp.json()
            messages = data.get("messages", [])
            errors = [m for m in messages if m.get("type") == "error"]
            warnings = [m for m in messages if m.get("type") in ("warning", "info")]
            error_summary = [f"L{m.get('lastLine', '?')}: {m.get('message', '')[:80]}" for m in errors[:5]]

            return {
                "success": True,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "errors": error_summary
            }
    except Exception as e:
        await logger.error(f"[W3C] Validation Failed: {e}")
        return {"success": False, "error": str(e)}
