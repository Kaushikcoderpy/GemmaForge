import aiohttp
from typing import Optional
from configuration_module import CONFIG
from logging_module import get_logger


# ==========================================
# GEMMA 4 INFERENCE ENDPOINTS
# ==========================================
GEMMA_2B_URL = "https://api.gemma4-hackathon.com/v1/models/gemma-4-2b/generate"
GEMMA_4B_URL = "https://api.gemma4-hackathon.com/v1/models/gemma-4-4b/generate"
GEMMA_26B_MOE_URL = "https://api.gemma4-hackathon.com/v1/models/gemma-4-26b-moe/generate"
GEMMA_31B_DENSE_URL = "https://api.gemma4-hackathon.com/v1/models/gemma-4-31b/generate"


async def _gemma_post(session: aiohttp.ClientSession, url: str, prompt: str, temp: float = 0.2) -> Optional[str]:
    """Internal helper to handle the raw HTTP POST to Gemma inference nodes."""
    logger = await get_logger()
    headers = {
        "Authorization": f"Bearer {CONFIG.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temp, "maxOutputTokens": 8192}
    }
    try:
        async with session.post(url, headers=headers, json=payload, timeout=120) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['candidates'][0]['content']['parts'][0]['text'].strip()
            await logger.error(f"[AI-CORE] Model {url} failed with status {resp.status}")
    except Exception as e:
        await logger.error(f"[AI-CORE] Inference Exception: {e}")
    return None


async def analyse_trends(session: aiohttp.ClientSession, raw_trends_json: str) -> Optional[str]:
    """
    JUSTIFICATION: USES GEMMA 4 4B.
    A 4B model is ideal for summarizing structured JSON data. It provides the linguistic
    precision needed to distinguish between 'noise' queries and 'high-intent' technical
    trends without the high inference cost or latency of a larger model.
    """
    logger = await get_logger()
    await logger.info("[AI-TRENDS] Summarizing rising queries with Gemma 4B...")

    prompt = f"""Review this Google Trends JSON. Identify the top 3-5 rising technical search terms. 
    Output a concise summary for a content planner.

    DATA: {raw_trends_json}
    """
    return await _gemma_post(session, GEMMA_4B_URL, prompt, temp=0.1)


async def plan_the_content(session: aiohttp.ClientSession, gap_report: str, trends_summary: str, human_style: str) -> \
Optional[str]:
    """
    JUSTIFICATION: USES GEMMA 4 26B MoE.
    Strategic planning is a high-reasoning task. The 26B MoE must synthesize competitor
    data, current trends, and stylistic constraints to architect a content structure.
    The output is not a blog post, but a 'Meta-Prompt' designed to guide the 31B writer.
    """
    logger = await get_logger()
    await logger.info("[AI-PLANNER] Designing Blueprint with Gemma 26B MoE...")

    prompt = f"""You are a Lead Content Architect. Design a technical blueprint for a blog post.
    Your output must be a sequence of instructions for a Writing Model (31B Dense).

    INPUT DATA:
    - Competitor Gaps: {gap_report}
    - Trends: {trends_summary}
    - Voice/Style: {human_style}

    BLUEPRINT REQUIREMENTS:
    1. Define 5 specific HTML <h2> sections.
    2. Set 'Depth Threshold' for each (e.g., 'Explain the heap-allocation failure in detail').
    3. Mandatory Analogies: Specify engineering-focused analogies for complex concepts.
    4. Code Specs: Define which libraries and versions must be used in code blocks.

    Output ONLY the detailed prompt blueprint for the writer.
    """
    return await _gemma_post(session, GEMMA_26B_MOE_URL, prompt, temp=0.3)


async def write_the_content(session: aiohttp.ClientSession, content_plan: str) -> Optional[str]:
    """
    JUSTIFICATION: USES GEMMA 4 31B DENSE.
    Writing technical content in valid HTML requires high instruction-following and
    sustained focus. A Dense 31B model is less prone to 'hallucinating' structural
    tags or breaking HTML syntax than an MoE, making it the superior 'Builder' for
    generating the final 2,000+ word technical payload.
    """
    logger = await get_logger()
    await logger.info("[AI-WRITER] Generating HTML Content with Gemma 31B Dense...")

    prompt = f"""You are a Principal Software Engineer. Execute this content blueprint.

    RULES:
    1. OUTPUT RAW HTML ONLY. Start with <h1> or <h2>. 
    2. No Markdown. No ```html delimiters. No conversational intros/outros.
    3. Use <h2>, <h3>, <p>, <ul>, and <pre><code>.
    4. Every code example must be production-ready and technically accurate.

    BLUEPRINT:
    {content_plan}
    """
    return await _gemma_post(session, GEMMA_31B_DENSE_URL, prompt, temp=0.2)


async def rewrite_for_syndication(session: aiohttp.ClientSession, html_content: str) -> Optional[str]:
    """
    JUSTIFICATION: USES GEMMA 4 4B.
    Rewriting existing content for a new platform (syndication) is a transformation
    task rather than an original creation. The 4B model has sufficient parameter
    density to summarize technical HTML into Markdown while maintaining the
    low latency needed for the concurrent distribution fan-out.
    """
    logger = await get_logger()
    await logger.info("[AI-SYNDICATOR] Synthesizing summary with Gemma 4B...")

    prompt = f"""Read this HTML blog post. Rewrite it into a punchy 300-word Markdown summary for social distribution.
    Rules: No jargon, zero AI filler, focus on the engineering solution.

    CONTENT: {html_content[:10000]}
    """
    return await _gemma_post(session, GEMMA_4B_URL, prompt, temp=0.4)


async def compress_competitor_fluff(session: aiohttp.ClientSession, raw_text: str) -> Optional[str]:
    """
    JUSTIFICATION: USES GEMMA 4 2B.
    This is a 'Map-Reduce' task performed on untrusted external data. We use the 2B
    edge model to strip marketing noise from competitor blogs, ensuring the
    downstream reasoning models receive only clean technical signal within their
    context windows.
    """
    logger = await get_logger()
    await logger.info("[AI-COMPRESSOR] Cleaning competitor context with Gemma 2B...")

    prompt = f"""Extract only technical facts, architecture decisions, and code-level concepts. 
    Discard all introductions, conclusions, and marketing fluff.

    TEXT: {raw_text[:12000]}
    """
    return await _gemma_post(session, GEMMA_2B_URL, prompt, temp=0.1)


async def generate_seo_gap_report(session: aiohttp.ClientSession, my_text: str, competitor_context: str) -> Optional[
    str]:
    """
    JUSTIFICATION: USES GEMMA 4 26B MoE.
    Comparative analysis between multiple technical documents is a reasoning-heavy
    task. The 26B MoE identifies 'negative space'—what competitors know that we
    missed—by logically evaluating the coverage of specific engineering sub-topics.
    """
    logger = await get_logger()
    await logger.info("[AI-GAP] Analyzing Competitor Gaps with Gemma 26B MoE...")

    prompt = f"""Compare my draft against the following competitor texts. 
    List exactly what technical sub-topics, edge cases, or code examples they covered that I LACK.

    MY DRAFT: {my_text[:8000]}
    COMPETITORS: {competitor_context}
    """
    return await _gemma_post(session, GEMMA_26B_MOE_URL, prompt, temp=0.2)