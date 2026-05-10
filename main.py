# main.py
import asyncio
import json
from typing import List

import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Internal Modules
import state_schema
import quality_gates
import serp_analysis
import intelligence
from broadcaster import fan_out_pipeline # Import the new fan_out_pipeline
from configuration_module import PostData, CONFIG
from logging_module import get_logger



@asynccontextmanager
async def lifespan(fastapi_app: FastAPI): # Renamed 'app' to 'fastapi_app'
    logger = await get_logger()
    await logger.info("[SYSTEM] Bootstrapping GemmaForge Orchestrator...")

    await state_schema.init_db()

    # Initialize Vector DB if it exists in your serp_analysis module
    if hasattr(serp_analysis, "init_vector_db"):
        await serp_analysis.init_vector_db()

    fastapi_app.state.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90))
    yield
    await logger.info("[SYSTEM] Tearing down connections...")
    await fastapi_app.state.session.close()


app = FastAPI(title="GemmaForge", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For hackathon: allow all. For prod: restrict to your domain.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ForgeRequest(BaseModel):
    raw_seed: str
    human_style: str


def format_sse(event_name: str, message: str, data: dict = None) -> str:
    """Formats payload strictly for Server-Sent Events (SSE)."""
    payload = {"event": event_name, "message": message}
    if data:
        payload.update(data)
    return f"data: {json.dumps(payload)}\n\n"


@app.post("/api/forge")
async def execute_publishing_pipeline(req: ForgeRequest, request: Request):
    """
    The God-Loop.
    Executes Idea -> SERP -> Plan -> Write -> Syndicate -> Quality -> Fan-Out.
    Yields real-time execution state to the frontend.
    """
    session = request.app.state.session
    logger = await get_logger()

    async def pipeline_stream():
        try:
            # ==========================================
            # PHASE 1: DATA INGESTION & TRENDS
            # ==========================================
            yield format_sse("phase_update", "Fetching SERP and Google Trends...")
            urls = await serp_analysis.fetch_organic_serp(session, req.raw_seed)

            trends_summary = "No trends found." # Default value since fetch_google_trends is removed

            # ==========================================
            # PHASE 2: COMPETITOR COMPRESSION (Gemma 2B)
            # ==========================================
            yield format_sse("phase_update", "Scraping and compressing competitor fluff...")
            texts_dict = await serp_analysis.extract_competitor_texts(urls)
            compressed_context = ""
            for url, text in texts_dict.items():
                compressed = await intelligence.compress_competitor_fluff(session, text)
                compressed_context += f"--- {url} ---\n{compressed}\n\n"

            # ==========================================
            # PHASE 3: GAP ANALYSIS (Gemma 26B MoE)
            # ==========================================
            yield format_sse("phase_update", "Calculating SEO gaps against competitors...")
            gap_report = await intelligence.generate_seo_gap_report(
                session,
                my_text=req.raw_seed,  # We compare our raw idea against their completed posts
                competitor_context=compressed_context
            )

            # ==========================================
            # PHASE 4: ARCHITECTURE PLANNING (Gemma 26B MoE)
            # ==========================================
            yield format_sse("phase_update", "Architecting content blueprint...")
            content_plan = await intelligence.plan_the_content(
                session, gap_report, trends_summary, req.human_style
            )
            content_plan = content_plan if content_plan is not None else "" # Handle potential None

            # ==========================================
            # PHASE 5: EXECUTION (Gemma 31B Dense)
            # ==========================================
            yield format_sse("phase_update", "Writing production HTML payload...")
            html_content = await intelligence.write_the_content(session, content_plan)
            html_content = html_content if html_content is not None else "" # Handle potential None

            # ==========================================
            # PHASE 6: SYNDICATION (Gemma 4B)
            # ==========================================
            yield format_sse("phase_update", "Generating omnichannel syndication text...")
            syndicated_text = await intelligence.rewrite_for_syndication(session, html_content)
            syndicated_text = syndicated_text if syndicated_text is not None else "" # Handle potential None

            # ------------------------------------------
            # Assemble the final data object
            # ------------------------------------------
            canonical_url = f"{CONFIG.BLOGGER_URL}/{req.raw_seed.replace(' ', '-').lower()}"
            post_data = PostData(
                title=f"Engineering Breakdown: {req.raw_seed.title()}",
                markdown_body=syndicated_text,
                canonical_url=canonical_url,
                post_summary=syndicated_text[:200] if syndicated_text else "", # Handle potential empty string
                html_content=html_content,
                syndicated_body=syndicated_text
            )

            # ==========================================
            # PHASE 7: QUALITY GATES
            # ==========================================
            yield format_sse("phase_update", "Running Quality Gates...")

            # Initialize state for quality gate results (no caching for now, re-run every time)
            # In a real scenario, you might want to persist these results in `state_schema`
            # and check for `use_cache` as in `distribute.py`.
            quality_gate_results = {}

            q_tasks = [
                asyncio.create_task(quality_gates.check_canonical_liveness(session, post_data.canonical_url)),
                asyncio.create_task(quality_gates.fetch_single_run(session, post_data.canonical_url, api_key=CONFIG.PSI_API, run_id=1)),
                asyncio.create_task(quality_gates.run_accessibility_audit(post_data.canonical_url)),
                asyncio.create_task(quality_gates.check_broken_images(session, post_data.html_content, post_data.canonical_url)),
                asyncio.create_task(quality_gates.validate_w3c_html(session, post_data.canonical_url))
            ]

            # Execute all quality gates concurrently
            liveness, psi_scores, axe_report, img_report, w3c_report = await asyncio.gather(*q_tasks, return_exceptions=True)

            # Store results for checks
            quality_gate_results["liveness"] = liveness
            quality_gate_results["psi_scores"] = psi_scores
            quality_gate_results["axe_report"] = axe_report
            quality_gate_results["images_report"] = img_report
            quality_gate_results["w3c_report"] = w3c_report

            # --- Gate 1: Canonical URL Liveness (HARD GATE) ---
            if isinstance(liveness, Exception) or not isinstance(liveness, dict) or not liveness.get("success"):
                failure_reason: str = f"CANONICAL URL DOWN: {post_data.canonical_url} is unreachable or check failed."
                await logger.error(f"🛑 {failure_reason}. Aborting pipeline.")
                yield format_sse("fatal_error", failure_reason)
                return
            yield format_sse("phase_update", "Canonical URL is live.")

            # --- Gate 2: PSI Scores (HARD GATE) ---
            if isinstance(psi_scores, Exception) or not isinstance(psi_scores, dict) or any(val is None for val in psi_scores.values()):
                failure_reason: str = "PageSpeed Insights could not verify all metrics or check failed. Aborting pipeline."
                await logger.error(f"🛑 {failure_reason}")
                yield format_sse("fatal_error", failure_reason)
                return

            avg_scores = psi_scores # Renaming for clarity
            failed_metrics: List[str] = [
                f"{c[:4].upper()}({avg_scores[c]:.1f}<{CONFIG.PSI_THRESHOLDS[c]})"
                for c in CONFIG.PSI_THRESHOLDS
                if avg_scores[c] < CONFIG.PSI_THRESHOLDS[c]
            ]
            if failed_metrics:
                failure_reason: str = f"PSI LOW: {', '.join(failed_metrics)}. Aborting pipeline."
                await logger.error(f"🛑 {failure_reason}")
                yield format_sse("fatal_error", failure_reason)
                return
            yield format_sse("phase_update", f"PageSpeed Insights scores are healthy: Perf({avg_scores['performance']:.1f}), Access({avg_scores['accessibility']:.1f}), BestP({avg_scores['best-practices']:.1f}), SEO({avg_scores['seo']:.1f})")

            # --- Gate 3: Axe-Core Accessibility (HARD GATE) ---
            if isinstance(axe_report, Exception) or not isinstance(axe_report, dict) or not axe_report.get("success"):
                failure_reason: str = f"Axe-Core audit failed or crashed: {axe_report if isinstance(axe_report, Exception) else axe_report.get('error', 'Unknown error')}. Aborting pipeline."
                await logger.error(f"🛑 {failure_reason}")
                yield format_sse("fatal_error", failure_reason)
                return
            
            critical_errors: int = axe_report.get("critical_count", 0)
            if critical_errors > 0:
                failure_reason: str = f"AXE CRITICAL ERRORS: {critical_errors} found | {axe_report.get('summary')}. Aborting pipeline."
                await logger.error(f"🛑 {failure_reason}")
                yield format_sse("fatal_error", failure_reason)
                return
            yield format_sse("phase_update", "Axe-Core: 0 Critical violations found. DOM is clean.")

            # --- Gate 4: Broken Images (SOFT GATE — warn only) ---
            if isinstance(img_report, Exception) or not isinstance(img_report, dict) or not img_report.get("success"):
                await logger.warning("⚠️ Broken image check failed. Proceeding anyway.")
                yield format_sse("phase_update", "Broken image check failed (proceeding).")
            elif img_report.get("broken_count", 0) > 0:
                await logger.warning(f"⚠️ {img_report['broken_count']} broken image(s) detected. Proceeding but fix these!")
                yield format_sse("phase_update", f"{img_report['broken_count']} broken image(s) detected (proceeding).")
            else:
                yield format_sse("phase_update", "Broken image check: All images healthy.")

            # --- Gate 5: W3C HTML Validation (SOFT GATE — warn only) ---
            if isinstance(w3c_report, Exception) or not isinstance(w3c_report, dict) or not w3c_report.get("success"):
                await logger.warning("⚠️ W3C validation failed. Proceeding anyway.")
                yield format_sse("phase_update", "W3C validation failed (proceeding).")
            elif w3c_report.get("error_count", 0) > 0:
                await logger.warning(f"⚠️ W3C: {w3c_report['error_count']} HTML errors found. Not blocking (Blogger HTML is messy).")
                yield format_sse("phase_update", f"W3C: {w3c_report['error_count']} HTML errors found (proceeding).")
            else:
                yield format_sse("phase_update", "W3C HTML validation: No errors found.")

            yield format_sse("phase_update", "All critical Quality Gates passed! Proceeding to broadcast.")

            # ==========================================
            # PHASE 8: CONCURRENT FAN-OUT
            # ==========================================
            yield format_sse("phase_update", "Initiating execution mesh (Broadcaster)...")
            current_state = await state_schema.load_state() # Load state for broadcaster
            async for update in fan_out_pipeline(session, post_data, current_state):
                # fan_out_pipeline yields dicts, format them for SSE
                yield format_sse(update["event"], update["message"], update.get("data"))
            yield format_sse("system_complete", "The Dharma Engine has completed the cycle.")

        except Exception as e:
            await logger.error(f"[PIPELINE FATAL] {e}")
            yield format_sse("fatal_error", str(e))

    return StreamingResponse(pipeline_stream(), media_type="text/event-stream")