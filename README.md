GemmaForge: The Async Publishing Pipeline

A fully asynchronous, local-first engine that transforms a raw technical seed into a deeply researched, self-refined blog post. It automates competitor gap analysis, drafts the content, distributes it across 10+ developer platforms, and instantly pings major search engines for indexing.

Built for the Major League Hacking Gemma 4 Challenge.

🏗 System Architecture & Stack

GemmaForge is built for speed and I/O efficiency. The entire stack is fully asynchronous, preventing blocking operations during heavy network requests (scraping, API broadcasts) and model inference.

The Async Stack:

Orchestration: FastAPI with WebSockets for real-time frontend telemetry.

Networking & Concurrency: aiohttp, asyncio, and tenacity (for exponential backoff/retries).

DOM Parsing: C-based LexborHTMLParser via selectolax (orders of magnitude faster than BeautifulSoup).

Vector/Embeddings: onnxruntime with Nomic Embed v1.5 INT8 (local, CPU-optimized execution).

Distribution APIs: atproto (Bluesky), mastodon, nostr_sdk, and direct GraphQL/REST integrations.

🧠 Intentional Model Selection (Gemma 4)

This system routes tasks to different hardware profiles based on the required cognitive load.

1. Gemma 4 26B MoE (The Analytical Engine)

Used for: SERP Gap Analysis, Drafting, and the "Critic-Refine" Loop.
Justification: Mixture-of-Experts is required for structural logic. Instead of just generating ideas, the 26B MoE actively analyzes the top-ranking Google results against the user's seed topic. It identifies exactly what competitors missed and constructs a strategic outline (e.g., "Cover these 3 common sections, but add these 2 novel edge cases to rank higher").

2. Gemma 4 2B (The Map-Reduce Worker)

Used for: SERP Data Compression and Tag Generation.
Justification: Feeding tens of thousands of words of raw HTML from SERP results into the MoE wastes context limits and degrades output. The 2B model is used strictly for fast, low-latency extraction—stripping marketing fluff from scraped competitor URLs and returning only dense, factual technical points.

⚙️ The Execution Pipeline

Targeting Phase: The user submits a raw seed topic (e.g., "Python AsyncIO Deadlocks"). The 26B MoE converts this into a high-intent Google Search query.

Scraping & Compression: The system fetches the top 3 SERP results. The 2B model compresses the raw HTML into strictly technical data points.

Gap Analysis: The 26B MoE reviews the competitor data and suggests a content outline based on what is present and what is missing (e.g., "Competitors missed loop blocking. Add 2 new sections on thread-pool executors").

Human Style Injection: (CRITICAL) To avoid generic AI formatting, the user must provide custom style instructions (e.g., "Write like a cynical Staff Engineer, use short sentences, zero corporate jargon, focus on the code.")

Draft & Refine: The 26B MoE writes the V1 draft. A secondary MoE prompt acts as a "Critic" to review the draft against the Human Style Injection and the Gap Analysis. A final pass refines the text.

Concurrent Fan-Out: The finalized markdown is pushed to the primary blog. The async daemon then concurrently broadcasts payloads to DEV.to, Hashnode, LinkedIn, Bluesky, Mastodon, Telegram, Paragraph, and Tumblr.

Instant Indexing: The pipeline immediately pings the Google Indexing API, Bing Webmaster API, and Yandex Recrawl queues to force immediate SERP presence, bypassing standard crawler delays.

📄 Example Output

(See the examples/ directory for full generated posts)

Topic Seed: The danger of using os.environ in Python multithreading.
Human Style: "Aggressive, code-first, no introductions."
MoE Gap Analysis: "Competitors mention thread safety but fail to show the CPython GIL context. Added section on C-level putenv race conditions."
Resulting Post Extract: > "You think os.environ is safe because Python has a GIL. You are wrong. Modifying the environment in a threaded Python application is a direct path to a segfault. The standard library relies on the underlying C library's putenv, which is notoriously not thread-safe. Here is the stack trace that will wake you up at 3 AM..."


🚀 Quick Start

Clone the repository and configure your .env file (see .env.example for required API keys).

Install dependencies: pip install -r requirements.txt

Launch the API: uvicorn main:app --reload

Access the UI at http://localhost:8000 to monitor the pipeline state via WebSockets
