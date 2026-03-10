"""

Semantic Search Engine using OpenAI Embeddings + Pinecone Vector DB.

Combines product title + description into a single embedding per product,
upserts them into Pinecone, and exposes a query function used by main.py.

"""

import os
import time
import logging
import argparse
from typing import Optional
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm

load_dotenv()
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX   = os.getenv("PINECONE_INDEX")
PINECONE_CLOUD   = os.getenv("PINECONE_CLOUD",   "aws")
PINECONE_REGION  = os.getenv("PINECONE_REGION",  "us-east-1")

EMBED_MODEL      = "text-embedding-3-small"   # 1536-dim, cheap & accurate
EMBED_DIM        = 1536
BATCH_SIZE       = 100                         # products per Pinecone upsert
EMBED_BATCH_SIZE = 50                          # products per OpenAI embed call

# ── DB Engine (reuses collaborative.py pattern) ───────────────────────────────

def _get_db_engine():
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "3306")
    name     = os.getenv("DB_NAME")
    user     = os.getenv("DB_USER")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))  # encodes @ → %40
    url      = f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
    return create_engine(url, pool_pre_ping=True)


# ── Clients ───────────────────────────────────────────────────────────────────

def _openai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")
    return OpenAI(api_key=OPENAI_API_KEY)


def _pinecone_index():
    """Connect to (or create) the Pinecone index and return it."""
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is not set in .env")

    pc = Pinecone(api_key=PINECONE_API_KEY)
    existing = [idx.name for idx in pc.list_indexes()]

    if PINECONE_INDEX not in existing:
        logger.info(f"🆕 Creating Pinecone index '{PINECONE_INDEX}' ...")
        pc.create_index(
            name      = PINECONE_INDEX,
            dimension = EMBED_DIM,
            metric    = "cosine",
            spec      = ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
        # Wait until ready
        while not pc.describe_index(PINECONE_INDEX).status["ready"]:
            logger.info("  ⏳ Waiting for index to be ready ...")
            time.sleep(3)
        logger.info(f"✅ Index '{PINECONE_INDEX}' created.")
    else:
        logger.info(f"✅ Using existing Pinecone index '{PINECONE_INDEX}'.")

    return pc.Index(PINECONE_INDEX)


# ── Text Preparation ──────────────────────────────────────────────────────────

def _build_text(title: Optional[str], description: Optional[str]) -> str:
    """
    Combine title and description into a single string for embedding.
    Title is repeated to give it slightly more weight.
    """
    title       = (title       or "").strip()
    description = (description or "").strip()

    if title and description:
        return f"{title}. {title}. {description}"
    return title or description or "unknown product"


# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI Embeddings API and return vectors."""
    response = client.embeddings.create(
        model = EMBED_MODEL,
        input = texts,
    )
    return [item.embedding for item in response.data]


# ── Indexing ──────────────────────────────────────────────────────────────────

def build_semantic_index(engine=None) -> dict:
    """
    Fetch all products from DB, embed title+description, upsert to Pinecone.
    Returns a summary dict.

    Args:
        engine: SQLAlchemy engine (optional — creates one if not provided)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    engine = engine or _get_db_engine()
    client = _openai_client()
    index  = _pinecone_index()

    # ── Fetch products ────────────────────────────────────────────────────────
    logger.info("📦 Fetching products from DB ...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                asin        AS product_id,
                title,
                description,
                stars       AS avg_rating,
                reviews     AS total_reviews,
                price,
                category_id
            FROM amazon_products
            WHERE title IS NOT NULL
              AND price > 0
        """)).fetchall()

    logger.info(f"  → {len(rows):,} products fetched.")

    if not rows:
        logger.warning("No products found — nothing to index.")
        return {"indexed": 0}

    # ── Batch embed + upsert ─────────────────────────────────────────────────
    total_indexed = 0
    products      = list(rows)

    # Process in embed-sized chunks
    for i in tqdm(range(0, len(products), EMBED_BATCH_SIZE), desc="Embedding & Upserting"):
        batch = products[i : i + EMBED_BATCH_SIZE]

        texts      = [_build_text(r.title, getattr(r, "description", None)) for r in batch]
        embeddings = _embed_texts(client, texts)

        vectors = []
        for row, embedding in zip(batch, embeddings):
            vectors.append({
                "id"      : str(row.product_id),
                "values"  : embedding,
                "metadata": {
                    "product_id"   : str(row.product_id),
                    "title"        : row.title        or "",
                    "avg_rating"   : float(row.avg_rating    or 0),
                    "total_reviews": int(row.total_reviews   or 0),
                    "price"        : float(row.price         or 0),
                    "category_id"  : str(row.category_id    or ""),
                },
            })

        # Upsert in Pinecone-safe batches
        for j in range(0, len(vectors), BATCH_SIZE):
            index.upsert(vectors=vectors[j : j + BATCH_SIZE])

        total_indexed += len(batch)

    logger.info(f"✅ Semantic index built — {total_indexed:,} products indexed in Pinecone.")
    return {"indexed": total_indexed}


# ── Query ─────────────────────────────────────────────────────────────────────

# Module-level singletons (initialised lazily on first query)
_openai_client_singleton = None
_pinecone_index_singleton = None


def _get_singletons():
    global _openai_client_singleton, _pinecone_index_singleton
    if _openai_client_singleton is None:
        _openai_client_singleton  = _openai_client()
        _pinecone_index_singleton = _pinecone_index()
    return _openai_client_singleton, _pinecone_index_singleton


def query_semantic_search(
    query      : str,
    top_n      : int   = 10,
    min_rating : float = 0.0,
    max_price  : Optional[float] = None,
    category_id: Optional[str]   = None,
) -> list[dict]:
    """
    Embed the query string and return the most semantically similar products
    from Pinecone.

    Args:
        query:       Free-text search query
        top_n:       Number of results to return
        min_rating:  Filter — minimum avg_rating (0.0–5.0)
        max_price:   Filter — maximum price (optional)
        category_id: Filter — specific category (optional)

    Returns:
        List of product dicts sorted by semantic similarity (descending).
    """
    client, index = _get_singletons()

    # Build Pinecone metadata filter
    filter_dict: dict = {}
    if min_rating > 0.0:
        filter_dict["avg_rating"] = {"$gte": min_rating}
    if max_price is not None:
        filter_dict["price"] = {"$lte": max_price}
    if category_id:
        filter_dict["category_id"] = {"$eq": category_id}

    # Embed the query
    query_vector = _embed_texts(client, [query])[0]

    # Query Pinecone
    response = index.query(
        vector          = query_vector,
        top_k           = top_n,
        include_metadata= True,
        filter          = filter_dict if filter_dict else None,
    )

    results = []
    for match in response.matches:
        meta = match.metadata or {}
        results.append({
            "product_id"      : meta.get("product_id"),
            "product_name"    : meta.get("title"),
            "avg_rating"      : meta.get("avg_rating"),
            "total_reviews"   : meta.get("total_reviews"),
            "price"           : meta.get("price"),
            "category_id"     : meta.get("category_id"),
            "similarity_score": round(match.score, 4),
        })

    return results


# ── Index Stats ───────────────────────────────────────────────────────────────

def get_index_stats() -> dict:
    """Return basic stats about the Pinecone index."""
    _, index = _get_singletons()
    stats    = index.describe_index_stats()
    return {
        "total_vectors"    : stats.total_vector_count,
        "index_name"       : PINECONE_INDEX,
        "embedding_model"  : EMBED_MODEL,
        "dimensions"       : EMBED_DIM,
    }


# ── CLI entry-point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Semantic Search Indexer")
    parser.add_argument(
        "--index",
        action  = "store_true",
        help    = "Fetch products from DB and build/refresh the Pinecone index",
    )
    parser.add_argument(
        "--stats",
        action  = "store_true",
        help    = "Print current Pinecone index stats",
    )
    parser.add_argument(
        "--query",
        type    = str,
        default = None,
        help    = "Test a semantic search query (e.g. --query 'wireless headphones')",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.index:
        build_semantic_index()

    if args.stats:
        import json
        print(json.dumps(get_index_stats(), indent=2))

    if args.query:
        import json
        results = query_semantic_search(args.query, top_n=5)
        print(f"\n🔍 Top results for: '{args.query}'\n")
        print(json.dumps(results, indent=2))