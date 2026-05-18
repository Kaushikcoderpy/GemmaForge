"""
GemmaForge Central Server — serves 3 HTML pages + all API endpoints
"""
import asyncio, logging, time, json, urllib.parse
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Request, UploadFile, File, Form
import base64
from typing import Dict
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── SSE log bridge ──────────────────────────────────────────────
log_q: asyncio.Queue = asyncio.Queue(maxsize=1000)

class AsyncSSELogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                item = {"level": record.levelname, "msg": self.format(record), "ts": int(time.time()*1000)}
                loop.call_soon_threadsafe(log_q.put_nowait, item)
        except Exception:
            pass

sse_handler = AsyncSSELogHandler()
sse_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(sse_handler)
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("gemmaforge.server")

@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("🚀 GemmaForge Server online.")
    yield
    logger.info("🛑 GemmaForge Server shutting down.")

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
if not ASSETS_DIR.exists():
    # If not in engine/, check parent (for dev flexibility)
    fallback = BASE_DIR.parent / "assets"
    if fallback.exists():
        ASSETS_DIR = fallback

app = FastAPI(title="GemmaForge API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Mount assets if they exist
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# Mount current directory to serve CSS/JS files
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")
# To make it easier for index.html which expects styles.css at root:
@app.get("/styles.css", include_in_schema=False)
async def styles(): return FileResponse(BASE_DIR / "styles.css")
@app.get("/app.js", include_in_schema=False)
async def app_js(): return FileResponse(BASE_DIR / "app.js")
@app.get("/ai_engine.js", include_in_schema=False)
async def ai_js(): return FileResponse(BASE_DIR / "ai_engine.js")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    logger.error(f"❌ Server Error: {error_msg}")
    # Extract the actual API error if possible
    if "APIError" in error_msg or "Generation failed" in error_msg:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"AI Engine Error: {error_msg}"}
        )
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"Internal Server Error: {error_msg}"}
    )

# ── SSE Log Stream ──────────────────────────────────────────────
@app.get("/logs/stream", tags=["Observability"])
async def stream_logs(request: Request):
    async def event_generator():
        yield 'data: {"level":"INFO","msg":"SSE connected.","ts":0}\n\n'
        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(log_q.get(), timeout=15.0)
                yield f"data: {json.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ── Atomic Tool Imports ─────────────────────────────────────────


async def _body_params(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    return {key: values[-1] for key, values in urllib.parse.parse_qs(raw.decode("utf-8", errors="ignore")).items()}

try:
    from content_gen import (
        compress_competitor_fluff_2b, analyse_trends_4b,
        generate_seo_gap_report_26b, plan_the_content_26b, write_the_content_31b,
        generate_alt_text_26b, extract_image_content_26b,
    )
except ImportError:
    from engine.content_gen import (
        compress_competitor_fluff_2b, analyse_trends_4b,
        generate_seo_gap_report_26b, plan_the_content_26b, write_the_content_31b,
        generate_alt_text_26b, extract_image_content_26b,
    )

@app.post("/tools/compress-fluff", tags=["Atomic Tools"])
async def api_compress_fluff(raw_text: str):
    """Gemma 2B — strip marketing noise, retain pure technical signal."""
    if len(raw_text) > 25000:
        return JSONResponse(status_code=413, content={"status": "error", "message": "Input exceeds 25,000 character limit."})
    logger.info("▶ compress_competitor_fluff_2b starting...")
    result = await compress_competitor_fluff_2b(raw_text)
    logger.info(f"✅ compress_fluff done. {len(result)} chars.")
    return {"status": "success", "result": result, "format": "markdown"}

@app.post("/tools/analyse-trends", tags=["Atomic Tools"])
async def api_analyse_trends(raw_trends_json: str):
    """Gemma 4B — identify 5 rising technical signals from Trends JSON."""
    if len(raw_trends_json) > 20000:
        return JSONResponse(status_code=413, content={"status": "error", "message": "Input exceeds 20,000 character limit."})
    logger.info("▶ analyse_trends_4b starting...")
    result = await analyse_trends_4b(raw_trends_json)
    logger.info(f"✅ analyse_trends done. {len(result)} chars.")
    return {"status": "success", "result": result, "format": "markdown"}

@app.post("/tools/seo-gap-report", tags=["Atomic Tools"])
async def api_seo_gap_report(my_text: str, competitor_context: str):
    """Gemma 26B — semantic delta analysis between your post and competitors."""
    if len(my_text) > 25000 or len(competitor_context) > 25000:
        return JSONResponse(status_code=413, content={"status": "error", "message": "Input exceeds 25,000 character limit."})
    logger.info("▶ generate_seo_gap_report_26b starting...")
    result = await generate_seo_gap_report_26b(my_text, competitor_context)
    logger.info(f"✅ seo_gap_report done. {len(result)} chars.")
    return {"status": "success", "result": result, "format": "markdown"}

@app.post("/tools/plan-content", tags=["Atomic Tools"])
async def api_plan_content(gap_report: str, trends_summary: str, human_style: str):
    """Gemma 26B — synthesize gap + trends into a structured meta-prompt blueprint."""
    if len(gap_report) > 20000 or len(trends_summary) > 10000:
        return JSONResponse(status_code=413, content={"status": "error", "message": "Input exceeds character limits (20k gap, 10k trends)."})
    logger.info("▶ plan_the_content_26b starting...")
    result = await plan_the_content_26b(gap_report, trends_summary, human_style)
    logger.info(f"✅ plan_content done. {len(result)} chars.")
    return {"status": "success", "result": result, "format": "markdown"}

@app.post("/tools/write-content", tags=["Atomic Tools"])
async def api_write_content(request: Request, content_plan: str = "", output_format: str = "html"):
    """Gemma 31B — generate production-ready HTML or Markdown from a blueprint."""
    body = await _body_params(request)
    content_plan = content_plan or body.get("content_plan", "")
    if len(content_plan) > 25000:
        return JSONResponse(status_code=413, content={"status": "error", "message": "Content plan exceeds 25,000 character limit."})
    output_format = output_format if output_format != "html" or "output_format" not in body else body.get("output_format", "html")
    if not content_plan.strip():
        return JSONResponse(status_code=400, content={"status": "error", "message": "content_plan is required"})
    logger.info(f"▶ write_the_content_31b starting (format={output_format}, input_chars={len(content_plan)})...")
    result = await write_the_content_31b(content_plan, output_format)
    logger.info(f"✅ write_content done. {len(result)} chars.")
    return {"status": "success", "result": result, "format": output_format}

@app.post("/tools/alt-text", tags=["Atomic Tools"])
async def api_alt_text(image: UploadFile = File(...)):
    """Gemma Vision — generate descriptive alt text for an image."""
    try:
        contents = await image.read()
        image_base64 = base64.b64encode(contents).decode("utf-8")
        mime_type = image.content_type or "image/jpeg"
        logger.info(f"▶ generate_alt_text_26b starting ({mime_type}, {len(contents)} bytes)...")
        result = await generate_alt_text_26b(image_base64, mime_type)
        logger.info(f"✅ alt_text done. {len(result)} chars.")
        return {"status": "success", "result": result, "format": "text"}
    except Exception as e:
        logger.error(f"Error in api_alt_text: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/tools/extract-image", tags=["Atomic Tools"])
async def api_extract_image(image: UploadFile = File(...), prompt: str = Form("")):
    """Gemma Vision — extract text, structural plan, or diagram data from an image."""
    try:
        contents = await image.read()
        image_base64 = base64.b64encode(contents).decode("utf-8")
        mime_type = image.content_type or "image/jpeg"
        logger.info(f"▶ extract_image_content_26b starting ({mime_type}, {len(contents)} bytes, prompt={prompt})...")
        result = await extract_image_content_26b(image_base64, mime_type, prompt)
        logger.info(f"✅ extract_image done. {len(result)} chars.")
        return {"status": "success", "result": result, "format": "markdown"}
    except Exception as e:
        logger.error(f"Error in api_extract_image: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/tools/image-to-article", tags=["Atomic Tools"])
async def api_image_to_article(image: UploadFile = File(...), prompt: str = Form(""), output_format: str = Form("html"), human_style: str = Form("")):
    """Gemma Vision Pipeline — extracts plan from image, plans it, and writes the article."""
    try:
        contents = await image.read()
        image_base64 = base64.b64encode(contents).decode("utf-8")
        mime_type = image.content_type or "image/jpeg"
        
        logger.info("▶ image-to-article step 1: extracting content...")
        extracted_content = await extract_image_content_26b(image_base64, mime_type, prompt)
        
        logger.info("▶ image-to-article step 2: planning content...")
        gap_report = "N/A - Image based generation"
        plan = await plan_the_content_26b(gap_report, extracted_content, human_style)
        
        logger.info("▶ image-to-article step 3: writing content...")
        article = await write_the_content_31b(plan, output_format)
        
        return {
            "status": "success",
            "extracted_content": extracted_content,
            "plan": plan,
            "result": article,
            "format": output_format
        }
    except Exception as e:
        logger.error(f"Error in api_image_to_article: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ── Engine Endpoints ────────────────────────────────────────────
@app.post("/engine/run", tags=["Full Engine"])
async def run_full_engine(
    run_quality_checks: bool = True,
    ping_search_engines: bool = True,
    syndicate_content: bool = True,
    topic: str = "",
    background_tasks: BackgroundTasks = None
):
    try:
        from distribution_engine import run_with_retries, log_listener
    except ImportError:
        from engine.distribution_engine import run_with_retries, log_listener
    
    try:
        log_listener.start()
    except Exception as e:
        logger.debug(f"Log listener status: {e}")
        
    async def _run():
        logger.info(f"🔥 Full Engine | QC={run_quality_checks} SE={ping_search_engines} Syn={syndicate_content} Topic={topic[:20]}")
        await run_with_retries(
            run_quality_checks=run_quality_checks,
            ping_search_engines=ping_search_engines,
            syndicate_content=syndicate_content,
            topic=topic,
        )
    background_tasks.add_task(_run)
    return {"status": "accepted", "mode": "full", "topic": topic}

@app.post("/engine/content-only", tags=["Full Engine"])
async def run_content_only_mode(topic: str = "", persona: str = "", background_tasks: BackgroundTasks = None):
    try:
        from distribution_engine import run_content_only, log_listener
    except ImportError:
        from engine.distribution_engine import run_content_only, log_listener

    try:
        log_listener.start()
    except Exception as e:
        logger.debug(f"Log listener status: {e}")

    async def _run():
        logger.info(f"🧠 Content-Only Mode: AI pipeline running. Topic: {topic[:20]} | Persona: {persona[:20]}")
        await run_content_only(topic=topic, persona=persona)
        logger.info("✅ Content-Only pipeline complete. No posts were made.")
    background_tasks.add_task(_run)
    return {"status": "accepted", "mode": "content-only", "topic": topic}

@app.get("/engine/latest-report", tags=["Full Engine"])
async def get_latest_report():
    report_path = BASE_DIR / "latest_content_report.md"
    if not report_path.exists():
        return {"content": None}
    
    try:
        # Using standard Path read for reliability
        content = report_path.read_text(encoding="utf-8")
        return {"content": content}
    except Exception as e:
        logger.error(f"Error reading report: {e}")
        return {"content": None, "error": str(e)}

@app.post("/engine/edit-content", tags=["Full Engine"])
async def edit_content_endpoint(request: Request):
    data = await request.json()
    instruction = data.get("instruction")

    from distribution_engine import edit_content, log_listener

        
    try:
        log_listener.start()
    except Exception as e:
        logger.debug(f"Log listener status: {e}")
        
    try:
        success = await edit_content(instruction)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Edit failed"}
    except Exception as e:
        logger.error(f"Edit error: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/run", tags=["Full Engine"])
async def run_pipeline(run_quality_checks: bool, ping_search_engines: bool, syndicate_content: bool) -> Dict[str, str]:
    # Start the log listener
    try:
        from distribution_engine import run_with_retries, log_listener
    except ImportError:
        from engine.distribution_engine import run_with_retries, log_listener

    try:
        log_listener.start()
    except RuntimeError:
        pass
    
    logger.info(f"Endpoint called with params: run_quality_checks={run_quality_checks}, ping_search_engines={ping_search_engines}, syndicate_content={syndicate_content}")
    asyncio.create_task(run_with_retries(
        run_quality_checks=run_quality_checks,
        ping_search_engines=ping_search_engines,
        syndicate_content=syndicate_content,
    ))
    
    return {"status": "Task submitted to background.", "details": "Check logs for progress."}

# ── Serve 3 Pages ───────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def serve_landing_root(): return FileResponse(BASE_DIR / "index.html")

@app.get("/index.html", include_in_schema=False)
async def serve_landing(): return FileResponse(BASE_DIR / "index.html")

@app.get("/tools.html", include_in_schema=False)
async def serve_tools(): return FileResponse(BASE_DIR / "tools.html")

@app.get("/engine.html", include_in_schema=False)
async def serve_engine(): return FileResponse(BASE_DIR / "engine.html")

@app.get("/demo.html", include_in_schema=False)
async def serve_demo(): return FileResponse(BASE_DIR / "demo.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
