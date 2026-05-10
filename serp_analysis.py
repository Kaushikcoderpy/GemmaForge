import asyncio
import aiohttp
import math
import hashlib
import json
import os
import aiosqlite
import trafilatura
from typing import List, Dict, Optional, Any
from logging_module import get_logger

# Use a separate DB for vectors to prevent locking the main state DB
VECTOR_DB_FILE = "gemmaforge_vectors.db"

async def init_vector_db():
    async with aiosqlite.connect(VECTOR_DB_FILE) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS vector_cache (
                hash_id TEXT PRIMARY KEY,
                vector_json TEXT
            )
        ''')
        await db.commit()

async def get_cached_vector(text_hash: str) -> Optional[List[float]]:
    logger = await get_logger()
    try:
        async with aiosqlite.connect(VECTOR_DB_FILE) as db:
            async with db.execute("SELECT vector_json FROM vector_cache WHERE hash_id = ?", (text_hash,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
    except Exception as e:
        await logger.error(f"Vector DB Read Error: {e}")
    return None

async def save_cached_vector(text_hash: str, vector: List[float]) -> None:
    try:
        async with aiosqlite.connect(VECTOR_DB_FILE) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(
                "INSERT INTO vector_cache (hash_id, vector_json) VALUES (?, ?) ON CONFLICT(hash_id) DO UPDATE SET vector_json=excluded.vector_json",
                (text_hash, json.dumps(vector))
            )
            await db.commit()
    except Exception as e:
        logger = await get_logger()
        await logger.error(f"Vector DB Save Error: {e}")

class NomicEmbedder:
    """Singleton for ONNX Runtime. Loaded once into memory."""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        import numpy as np
        import onnxruntime as ort
        from transformers import AutoTokenizer
        from huggingface_hub import hf_hub_download

        self.np = np
        self.model_id = "Xenova/nomic-embed-text-v1"
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        os.makedirs(cache_dir, exist_ok=True)
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, cache_dir=cache_dir, local_files_only=False
        )
        
        model_path = hf_hub_download(
            repo_id=self.model_id, filename="onnx/model_quantized.onnx", cache_dir=cache_dir
        )
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

    def embed(self, texts: List[str]) -> List[List[float]]:
        np = self.np
        encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=8192, return_tensors="np")
        
        inputs = {
            "input_ids": encoded["input_ids"].astype(np.int64),
            "attention_mask": encoded["attention_mask"].astype(np.int64),
            "token_type_ids": encoded["token_type_ids"].astype(np.int64)
        }
        
        outputs = self.session.run(None, inputs)
        token_embeddings = outputs[0]
        
        mask = encoded["attention_mask"]
        input_mask_expanded = np.expand_dims(mask, axis=-1).astype(float)
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
        sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        
        pooled = sum_embeddings / sum_mask
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / norms).tolist()

def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    return dot_product / (norm_v1 * norm_v2) if norm_v1 and norm_v2 else 0.0

async def fetch_organic_serp(session: aiohttp.ClientSession, query: str) -> List[str]:
    logger = await get_logger()
    await logger.info(f"[SERP] Fetching top organic results for '{query}'...")
    # NOTE: Set your SERPAPI_KEY in the environment or config.
    api_key = os.getenv("SERPAPI_KEY", "")
    params = {"engine": "google", "q": query, "num": "5", "api_key": api_key}
    try:
        async with session.get("https://serpapi.com/search", params=params) as response:
            if response.status == 200:
                data = await response.json()
                links = [res.get("link") for res in data.get("organic_results", [])][:3]
                return [l for l in links if l]
    except Exception as e:
        await logger.error(f"[SERP] Fetch Exception: {e}")
    return []

async def extract_competitor_texts(urls: List[str]) -> Dict[str, str]:
    logger = await get_logger()

    def extract(urlx):
        downloaded = trafilatura.fetch_url(urlx)
        if downloaded:
            return trafilatura.extract(downloaded, include_links=False, include_images=False, include_tables=False)
        return None

    async def fetch_and_extract(url):
        await logger.info(f"[SERP] Trafilatura extracting: {url}...")
        try:
            # CPU blocking task, offload to thread
            text = await asyncio.to_thread(extract, url)
            return url, text
        except Exception as e:
            await logger.error(f"[SERP] Extraction failed for {url}: {e}")
            return url, None

    results = await asyncio.gather(*(fetch_and_extract(url) for url in urls))
    return {url: text for url, text in results if text}

async def analyze_gaps_via_embeddings(my_text: str, comp_texts: Dict[str, str]) -> Dict[str, Any]:
    """Generates the context string based on Vector Similarity."""
    logger = await get_logger()
    await init_vector_db()

    if not comp_texts:
        return {"lowest_urls": [], "competitor_scores": {}, "competitor_context": ""}

    urls = list(comp_texts.keys())
    texts_to_embed = [my_text] + [comp_texts[u] for u in urls]
    
    results = []
    texts_for_onnx = []
    indices_for_onnx = []

    # Check SQLite cache first
    for i, text in enumerate(texts_to_embed):
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        cached_vec = await get_cached_vector(text_hash)
        if cached_vec:
            results.append(cached_vec)
        else:
            results.append(None)
            texts_for_onnx.append(text)
            indices_for_onnx.append(i)

    # Compute missing embeddings via ONNX
    if texts_for_onnx:
        await logger.info(f"[ONNX] Computing {len(texts_for_onnx)} new embeddings...")
        embedder = NomicEmbedder.get_instance()
        new_vectors = await asyncio.to_thread(embedder.embed, texts_for_onnx)
        
        for idx, vec in zip(indices_for_onnx, new_vectors):
            results[idx] = vec
            text_hash = hashlib.md5(texts_to_embed[idx].encode('utf-8')).hexdigest()
            await save_cached_vector(text_hash, vec)

    my_emb = results[0]
    comp_embs = results[1:]
    
    scores = {}
    for i, u in enumerate(urls):
        similarity = _cosine_similarity(my_emb, comp_embs[i])
        rank_position = i + 1
        gap_score = (1 - similarity) * (1 / rank_position)
        scores[u] = gap_score
        await logger.info(f"[SERP] Rank {rank_position} | Sim: {similarity:.3f} | Gap Score: {gap_score:.3f}")

    sorted_urls = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    priority_urls = sorted_urls[:3]
    
    competitor_context = ""
    for u in priority_urls:
        competitor_context += f"--- COMPETITOR: {u} ---\n{comp_texts[u][:15000]}\n\n"
        
    return {
        "lowest_urls": priority_urls,
        "competitor_scores": scores,
        "competitor_context": competitor_context
    }
