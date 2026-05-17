import hashlib
import logging
import os
import re
import aiohttp
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from dotenv import load_dotenv

# CENTRALIZED INITIALIZATION & IMPORTS
load_dotenv()
logger = logging.getLogger("gemmaforge.content")

class ModelNotAvailableError(Exception):
    pass

class APIError(Exception):
    pass

def _get_api_key():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set.")
    return api_key

async def _get_target_model(session: aiohttp.ClientSession, requested_name: str, fallback_keywords: list = None) -> str:
    """Dynamically checks Google API for available models and returns the best match."""
    api_key = _get_api_key()
    models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    async with session.get(models_url) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise APIError(f"Failed to fetch models: {text}")
        data = await resp.json()
        
    available_models = [m['name'].replace('models/', '') for m in data.get('models', [])]
    
    if requested_name in available_models:
        return requested_name
        
    gemma_models = [m for m in available_models if "gemma" in m]
    if not gemma_models:
        raise ModelNotAvailableError("No Gemma models available in this API key.")
        
    if fallback_keywords:
        for kw in fallback_keywords:
            for m in gemma_models:
                if kw in m:
                    return m
    return gemma_models[0]

def _normalize_for_echo_check(text: str) -> str:
    return " ".join(text.lower().split())

def _looks_like_echo(result: str, source: str) -> bool:
    """Detect the failure mode where the model returns the prompt/blueprint itself."""
    result_norm = _normalize_for_echo_check(result)
    source_norm = _normalize_for_echo_check(source)
    if not result_norm or not source_norm:
        return False

    first_source_line = next((line.strip() for line in source.splitlines() if line.strip()), "")
    if first_source_line and result.strip().startswith(first_source_line):
        return True

    blueprint_markers = [
        "complete, full-length technical article",
        "minimum 1000 words",
        "code example",
        "constraint check",
        "no meta-commentary",
        "raw markdown only",
        "raw html",
    ]
    marker_hits = sum(1 for marker in blueprint_markers if marker in result_norm)
    if marker_hits >= 3 and len(result_norm) <= max(len(source_norm) * 2, 900):
        return True

    source_lines = [line.strip() for line in source.splitlines() if len(line.strip()) > 18]
    if source_lines:
        echoed = sum(1 for line in source_lines if _normalize_for_echo_check(line) in result_norm)
        if echoed >= max(4, int(len(source_lines) * 0.35)):
            return True

    return False

def _strip_generation_wrappers(result: str, output_format: str) -> str:
    cleaned = result.strip()
    lowered = output_format.lower()
    if lowered in ["md", "markdown"] and cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    if lowered not in ["md", "markdown"]:
        for marker in ["<h1", "<article", "<section"]:
            idx = cleaned.lower().find(marker)
            if idx > 0:
                cleaned = cleaned[idx:].strip()
                break
    return cleaned

def _clean_blueprint_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^\s*[*\-]+\s*", "", cleaned)
    cleaned = cleaned.strip("* ")
    cleaned = cleaned.replace("*:", ":").replace(":*", ":")
    return re.sub(r"\s+", " ", cleaned)

def _build_article_contract(content_plan: str, output_format: str) -> str:
    """Pass-through the contract, avoiding variable extraction that hallucinates topics."""
    format_line = (
        "Output MUST be raw Markdown only with one title line, ## section headers, code blocks, and paragraphs."
        if output_format.lower() in ["md", "markdown"]
        else "Output MUST be raw HTML only with h1/h2/h3/p/pre/code/ul/li tags and no Markdown."
    )
    
    return f"{content_plan}\n\n[FORMAT ENFORCEMENT]:\n{format_line}"


async def _generate_with_gemma(
    session: aiohttp.ClientSession,
    model_name: str,
    prompt: str,
    generation_config: dict,
    timeout_seconds: int,
    system_instruction: str = "",
    safety_settings: list = None
) -> str:
    api_key = _get_api_key()
    generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    if safety_settings:
        payload["safetySettings"] = safety_settings
    async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as gen_resp:
        if gen_resp.status != 200:
            text = await gen_resp.text()
            if system_instruction:
                # Gemma model rejected systemInstruction — bake it into the prompt instead
                logger.warning("Gemma rejected systemInstruction on %s (HTTP %s); inlining into prompt.", model_name, gen_resp.status)
                logger.debug("API rejection detail: %s", text[:300])
                payload.pop("systemInstruction", None)
                # Prepend system context directly into the user message
                original_prompt = payload["contents"][0]["parts"][0]["text"]
                payload["contents"][0]["parts"][0]["text"] = (
                    f"SYSTEM CONTEXT: {system_instruction}\n\n{original_prompt}"
                )
                async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as retry_resp:
                    if retry_resp.status == 200:
                        data = await retry_resp.json()
                        return data['candidates'][0]['content']['parts'][0]['text']
                    # Second retry also failed — might be thinkingConfig causing the issue
                    retry_text = await retry_resp.text()
                    if "thinkingConfig" in str(retry_text) or retry_resp.status == 400:
                        logger.warning("Stripping thinkingConfig from %s (likely unsupported).", model_name)
                        payload["generationConfig"].pop("thinkingConfig", None)
                        async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as final_resp:
                            if final_resp.status == 200:
                                data = await final_resp.json()
                                return data['candidates'][0]['content']['parts'][0]['text']
                            text = await final_resp.text()
                    else:
                        text = retry_text
            raise APIError(f"Generation failed: {text}")
        data = await gen_resp.json()
        return data['candidates'][0]['content']['parts'][0]['text']

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type((aiohttp.ClientError, APIError, asyncio.TimeoutError)))
async def compress_competitor_fluff_2b(raw_text: str) -> str:
    """
    Task: Strip marketing noise from raw text to extract pure technical signal.
    Justification: The 2B model is perfect for aggressive signal extraction and noise reduction. 
    It excels at filtering and summarization tasks where high-level reasoning isn't as critical as speed.
    """
    api_key = _get_api_key()
    prompt = f"""Perform aggressive signal extraction on the provided text.
    Discard all marketing copy, introductions, self-promotional filler, and 'thought' transitions.
    Retain only hard technical data: version numbers, library names, code logic, and architectural constraints.
    
    INPUT TEXT:
    {raw_text[:12000]}
    
    OUTPUT: A high-density technical summary."""

    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    async with aiohttp.ClientSession(connector=connector) as session:
        target_model = await _get_target_model(session, "gemma-4-26b-a4b-it", ["2b", "27b"])
        generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=240)) as gen_resp:
            if gen_resp.status != 200:
                text = await gen_resp.text()
                raise APIError(f"Generation failed: {text}")
            data = await gen_resp.json()
            return data['candidates'][0]['content']['parts'][0]['text']

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type((aiohttp.ClientError, APIError, asyncio.TimeoutError)))
async def analyse_trends_4b(raw_trends_json: str) -> str:
    """
    Task: Identify rising technical search terms from Google Trends JSON.
    Justification: The 4B model provides a sweet spot for pattern recognition in structured data like JSON.
    It can efficiently identify themes and emerging signals without the overhead of larger models.
    """
    api_key = _get_api_key()
    prompt = f"""Review the following Google Trends raw JSON data.
    Identify exactly 5 emerging technical signals or engineering themes that demonstrate high growth.
    Filter for specific libraries, frameworks, or architecture patterns. Discard general consumer topics.
    
    RAW DATA:
    {raw_trends_json}
    
    OUTPUT: A technical briefing for a lead architect."""

    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    async with aiohttp.ClientSession(connector=connector) as session:
        target_model = await _get_target_model(session, "gemma-4-26b-a4b-it", ["4b", "27b"])
        generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=240)) as gen_resp:
            if gen_resp.status != 200:
                text = await gen_resp.text()
                raise APIError(f"Generation failed: {text}")
            data = await gen_resp.json()
            return data['candidates'][0]['content']['parts'][0]['text']

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type((aiohttp.ClientError, APIError, asyncio.TimeoutError)))
async def generate_seo_gap_report_26b(my_text: str, competitor_context: str) -> str:
    """
    Task: Analyze technical gaps between idea and competitor content.
    Justification: This task requires deep comparative analysis and understanding of technical nuances.
    The 26B model is equipped with the necessary parameter count to perform differential analysis effectively.
    """
    api_key = _get_api_key()
    prompt = f"""Execute a differential technical analysis between my content and the provided competitor context.
    Identify the 'Semantic Delta': specific technical sub-domains, edge-case scenarios, or implementation details present in their work but missing from mine.
    
    MY TEXT: 
    {my_text[:8000]}
    
    COMPETITOR CONTEXT: 
    {competitor_context}
    
    OUTPUT: A prioritized list of technical deficits and recommended inclusions."""

    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    async with aiohttp.ClientSession(connector=connector) as session:
        target_model = await _get_target_model(session, "gemma-4-26b-a4b-it", ["27b", "26b"])
        generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=240)) as gen_resp:
            if gen_resp.status != 200:
                text = await gen_resp.text()
                raise APIError(f"Generation failed: {text}")
            data = await gen_resp.json()
            return data['candidates'][0]['content']['parts'][0]['text']

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5), retry=retry_if_exception_type((aiohttp.ClientError, APIError, asyncio.TimeoutError)))
async def plan_the_content_26b(gap_report: str, trends_summary: str, human_style: str) -> str:
    """
    Task: Design a technical blueprint (meta-prompt) for the writing phase.
    Justification: Creating a comprehensive technical blueprint demands strong structural reasoning and 
    synthesis of multiple inputs. The 26B model is ideal for generating coherent, logical meta-prompts.
    """
    api_key = _get_api_key()
    prompt = f"""As a Lead Content Architect, construct a high-fidelity technical blueprint for a deep-dive engineering article.
    Synthesize the provided gap analysis and trends into a structured 'Meta-Prompt' for a writing engine.
    
    GAP REPORT: {gap_report}
    TRENDS SUMMARY: {trends_summary}
    CONSTRAINTS (STYLE): {human_style}
    
    OUTPUT: A sequence of discrete, actionable instructions for a content generator. Focus on technical depth and code-priority."""

    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    async with aiohttp.ClientSession(connector=connector) as session:
        target_model = await _get_target_model(session, "gemma-4-26b-a4b-it", ["27b", "26b"])
        generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        async with session.post(generate_url, json=payload, timeout=aiohttp.ClientTimeout(total=240)) as gen_resp:
            if gen_resp.status != 200:
                text = await gen_resp.text()
                raise APIError(f"Generation failed: {text}")
            data = await gen_resp.json()
            return data['candidates'][0]['content']['parts'][0]['text']

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3), retry=retry_if_exception_type((aiohttp.ClientError, APIError, asyncio.TimeoutError)))
async def write_the_content_31b(content_plan: str, output_format: str = "html", persona: str = "") -> str:
    """
    Task: Generate production-ready content from a topic brief.
    Uses Output Anchoring and a single-turn jailbreak to prevent echoes.
    """
    import json
    api_key = _get_api_key()
    is_md = output_format.lower() in ["md", "markdown"]
    anchor = "#" if is_md else "<h1>"
    contract = _build_article_contract(content_plan, output_format)
    
    base_rules = (
        "Rules: 1. Start with a visceral, narrative hook. 2. Weave relevant data into the story. "
        "3. Use active, conversational verbs. 4. No 'Introduction' or 'Hardware' headers. "
        "5. Output ONLY final, production-ready prose. No plans. No conversational filler. No echoes."
    )
    if persona:
        system_instruction = f"Persona: {persona}\n\n{base_rules}"
    else:
        system_instruction = f"Persona: You are a Senior Technical Writer with a visceral, human-centric style.\n\n{base_rules}"

    final_prompt = f"""Write a final, production-ready technical article based on this data.
[DATA SOURCE]:
{contract}

[STRICT COMMAND]: Transform the data above into a high-engagement, human-centric article.
[STRICT RULE]: Start the article immediately. Do NOT echo the prompt. Do NOT explain your plan."""

    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Re-enabling 31B because Prefilling (below) stops the CoT leak
        target_model = await _get_target_model(session, "gemma-4-31b-it", ["31b", "27b", "26b"])
        
        # Temperature raised to 0.7 to break the deterministic echoing loop
        generation_config = {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
            "topP": 0.95
        }
        
        generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        
        # RESPONSE PREFILLING: Force the model to start with the anchor
        # This is the strongest anti-echo/anti-plan measure possible.
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": final_prompt}]},
                {"role": "model", "parts": [{"text": anchor}]}
            ],
            "generationConfig": generation_config,
            "systemInstruction": {"parts": [{"text": system_instruction}]}
        }

        async def _attempt_gen(current_payload):
            async with session.post(generate_url, json=current_payload, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    if "systemInstruction" in err or resp.status == 400:
                        # Fallback: Move system instruction to the user message if the API rejects it
                        new_payload = {
                            "contents": [
                                {"role": "user", "parts": [{"text": f"{system_instruction}\n\n{final_prompt}"}]},
                                {"role": "model", "parts": [{"text": anchor}]}
                            ],
                            "generationConfig": generation_config
                        }
                        async with session.post(generate_url, json=new_payload, timeout=aiohttp.ClientTimeout(total=240)) as retry_resp:
                            if retry_resp.status != 200:
                                raise APIError(f"Generation failed after fallback: {await retry_resp.text()}")
                            return await retry_resp.json()
                    raise APIError(f"Generation failed (HTTP {resp.status}): {err}")
                return await resp.json()

        data = await _attempt_gen(payload)
        
        try:
            result = data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            reason = data.get('candidates', [{}])[0].get('finishReason', 'UNKNOWN')
            raise APIError(f"Model failed to return text. Reason: {reason}. Full response: {json.dumps(data)}")

        # Make sure the anchor is still there (cleanly)
        if not result.strip().startswith(anchor):
            result = anchor + " " + result.lstrip("# \n") if is_md else anchor + result
        
        result = _strip_generation_wrappers(result, output_format)
        
        # Final strict fallback if it somehow still echoes
        if _looks_like_echo(result, content_plan) or _looks_like_echo(result, contract):
            strict_prompt = f"{system_instruction}\n\n[CRITICAL FAILURE]: You wrote a plan/echo. You MUST write the actual narrative article NOW.\n[RULE]: Visceral opening. Narrative flow. No headers like 'Introduction'.\n\nDATA:\n{contract}\n\nOUTPUT FINAL ARTICLE PROSE ONLY:"
            strict_payload = {
                "contents": [{"role": "user", "parts": [{"text": strict_prompt}]}],
                "generationConfig": generation_config
            }
            async with session.post(generate_url, json=strict_payload, timeout=aiohttp.ClientTimeout(total=240)) as final_resp:
                if final_resp.status == 200:
                    data = await final_resp.json()
                    result = data['candidates'][0]['content']['parts'][0]['text']
                    if not result.strip().startswith(anchor):
                        result = anchor + " " + result.lstrip("# \n") if is_md else anchor + result
                    result = _strip_generation_wrappers(result, output_format)

        return result
