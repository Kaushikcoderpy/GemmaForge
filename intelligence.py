import aiohttp
from typing import Optional
from selectolax.parser import HTMLParser
from configuration_module import CONFIG
from logging_module import get_logger

import asyncio

async def _gemma_post(
    session: aiohttp.ClientSession, 
    model: str, 
    prompt: str, 
    api_key: Optional[str] = None, 
    temp: float = 0.2
):
    """
    Modular helper for Google AI Studio inference.
    Yields status updates and finally the result string.
    """
    key = api_key or CONFIG.GOOGLE_API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {
            "parts": [{"text": "ACT AS A RAW DATA EMITTER. YOU ARE NOT A CHATBOT. NEVER output reasoning, checklists, confidence scores, intros, structures, or 'thinking' traces. Output ONLY the requested technical payload (HTML or Markdown). Start your response immediately. If you include any conversational filler, the system will crash."}]
        },
        "contents": [
            {
                "role": "user", 
                "parts": [{"text": "TASK: Transform blueprint to HTML.\nINPUT: Title: Test\nPAYLOAD START:"}]
            },
            {
                "role": "model", 
                "parts": [{"text": "<html><body><h1>Test</h1></body></html>"}]
            },
            {
                "role": "user", 
                "parts": [{"text": f"TASK: Generate technical payload.\nINPUT:\n{prompt}\n\nPAYLOAD START:"}]
            }
        ],
        "generationConfig": {
            "temperature": temp, 
            "maxOutputTokens": 8192,
            "stopSequences": ["PAYLOAD END", "Analysis:", "Check:", "Structure:", "Topic:", "Confidence Score:"]
        }
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.post(url, headers=headers, json=payload, timeout=120) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    yield {"status": "success", "data": data['candidates'][0]['content']['parts'][0]['text'].strip()}
                    return
                
                # Retry on transient server errors (500, 503, etc.)
                if resp.status in [500, 503, 504] and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    yield {"status": "retry", "message": f"Transient error {resp.status}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})..."}
                    await asyncio.sleep(wait_time)
                    continue

                # Log final failure
                error_text = await resp.text()
                yield {"status": "error", "message": f"AI Engine Error ({resp.status}): {error_text[:200]}"}
                return
        except Exception as e:
            if attempt < max_retries - 1:
                yield {"status": "retry", "message": f"Connection error. Retrying in 2s..."}
                await asyncio.sleep(2)
                continue
            yield {"status": "error", "message": f"Inference Exception: {str(e)}"}
            return

async def analyse_trends(session: aiohttp.ClientSession, raw_trends_json: str, api_key: Optional[str] = None):
    """Identify rising technical search terms from Google Trends JSON."""
    model = CONFIG.GEMMA_26B_MODEL
    prompt = f"""Review this Google Trends JSON. Identify the top 3-5 rising technical search terms. 
    Output a concise summary for a content planner.
    DATA: {raw_trends_json}"""
    async for event in _gemma_post(session, model, prompt, api_key=api_key, temp=0.1):
        yield event

async def generate_seo_gap_report(session: aiohttp.ClientSession, my_text: str, competitor_context: str, api_key: Optional[str] = None):
    """Analyze technical gaps between your idea and competitor content."""
    if not my_text: yield {"status": "error", "message": "Missing input text"}; return
    model = CONFIG.GEMMA_26B_MODEL
    prompt = f"""Compare my draft against the following competitor texts. 
    List exactly what technical sub-topics, edge cases, or code examples they covered that I LACK.
    MY DRAFT: {my_text[:8000]}
    COMPETITORS: {competitor_context}
    OUTPUT RULE: JSON or Bullet points only. No conversational filler."""
    async for event in _gemma_post(session, model, prompt, api_key=api_key, temp=0.2):
        yield event

async def plan_the_content(session: aiohttp.ClientSession, gap_report: str, trends_summary: str, human_style: str, api_key: Optional[str] = None):
    """Design a technical blueprint (meta-prompt) for the writing phase."""
    if not gap_report: yield {"status": "error", "message": "Missing gap report"}; return
    model = CONFIG.GEMMA_26B_MODEL
    prompt = f"""You are a Lead Content Architect. Design a technical blueprint for a blog post.
    INPUT DATA:
    - Competitor Gaps: {gap_report}
    - Trends: {trends_summary}
    - Voice/Style: {human_style}
    OUTPUT RULE: Provide a sequence of instructions for a Writing Model. 
    DO NOT include any intro, outro, or reasoning. Output the PLAN ONLY."""
    async for event in _gemma_post(session, model, prompt, api_key=api_key, temp=0.3):
        yield event

async def write_the_content(session: aiohttp.ClientSession, content_plan: Optional[str] = None, api_key: Optional[str] = None):
    """Generate production-ready HTML content from a blueprint or raw instructions."""
    if not content_plan:
        yield {"status": "error", "message": "No content plan or blueprint provided."}
        return
    
    model = CONFIG.GEMMA_31B_MODEL
    prompt = f"""Transform the following technical blueprint into production-ready HTML code.
    TECHNICAL BLUEPRINT:
    {content_plan}
    
    REQUIREMENTS:
    - NO Markown. NO conversational filler.
    - Output 100% RAW HTML content only."""
    async for event in _gemma_post(session, model, prompt, api_key=api_key, temp=0.2):
        yield event

async def rewrite_for_syndication(session: aiohttp.ClientSession, html_content: str, api_key: Optional[str] = None):
    """Convert technical HTML into a punchy Markdown summary for social media."""
    if not html_content: yield {"status": "error", "message": "Missing content"}; return
    model = CONFIG.GEMMA_31B_MODEL
    text_content = HTMLParser(html_content).text(separator=' ')
    prompt = f"""Summarize the following technical content into a punchy 300-word Markdown post.
    CONTENT:
    {text_content}
    
    REQUIREMENTS:
    - Focus on the engineering solution.
    - NO jargon, NO AI filler, NO preamble.
    - Output ONLY the Markdown content."""
    async for event in _gemma_post(session, model, prompt, api_key=api_key, temp=0.4):
        yield event

async def compress_competitor_fluff(session: aiohttp.ClientSession, raw_text: str, api_key: Optional[str] = None):
    """Strip marketing noise from raw text to extract pure technical signal."""
    if not raw_text: yield {"status": "error", "message": "Missing input"}; return
    model = CONFIG.GEMMA_26B_MODEL
    prompt = f"""Extract only technical facts, architecture decisions, and code-level concepts. 
    Discard all introductions, conclusions, and marketing fluff.
    OUTPUT RULE: Raw technical data only. No intro/outro.
    TEXT: {raw_text[:12000]}"""
    async for event in _gemma_post(session, model, prompt, api_key=api_key, temp=0.1):
        yield event