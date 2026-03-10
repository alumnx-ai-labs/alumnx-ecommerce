"""

Elasticsearch-powered keyword search engine for Amazon products.

Features:
  - Full-text search across title, category, and description
  - Fuzzy matching (typo-tolerant)
  - Boosted relevance scoring (title > category > description)
  - Price range & min-rating filters
  - Index builder that pulls products from your MySQL DB via SQLAlchemy
"""

import os
import logging
from typing import Optional

from elasticsearch import Elasticsearch, helpers
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

ES_HOST  = os.getenv("ES_HOST",  "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "amazon_products")

# ── Client ────────────────────────────────────────────────────────────────────

def get_es_client() -> Elasticsearch:
    """Return a connected Elasticsearch client."""
    client = Elasticsearch(ES_HOST)
    if not client.ping():
        raise ConnectionError(f"Cannot reach Elasticsearch at {ES_HOST}")
    logger.info(f"✓ Connected to Elasticsearch at {ES_HOST}")
    return client


# ── Index Management ──────────────────────────────────────────────────────────

INDEX_MAPPING = {
    "settings": {
        "analysis": {
            "analyzer": {
                "product_analyzer": {
                    "type"      : "custom",
                    "tokenizer" : "standard",
                    "filter"    : ["lowercase", "stop", "snowball"],
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "product_id"   : {"type": "keyword"},
            "product_name" : {
                "type"    : "text",
                "analyzer": "product_analyzer",
                "fields"  : {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "category"     : {
                "type"    : "text",
                "analyzer": "product_analyzer",
                "fields"  : {"keyword": {"type": "keyword"}},
            },
            "description"  : {"type": "text", "analyzer": "product_analyzer"},
            "avg_rating"   : {"type": "float"},
            "total_reviews": {"type": "integer"},
            "price"        : {"type": "float"},
            "category_id"  : {"type": "keyword"},
            "img_url"      : {"type": "keyword", "index": False},
            "product_url"  : {"type": "keyword", "index": False},
        }
    },
}


def create_index(es: Elasticsearch, recreate: bool = False) -> None:
    """Create the ES index. Set recreate=True to wipe and rebuild."""
    if es.indices.exists(index=ES_INDEX):
        if recreate:
            es.indices.delete(index=ES_INDEX)
            logger.info(f"🗑  Deleted existing index '{ES_INDEX}'")
        else:
            logger.info(f"✓ Index '{ES_INDEX}' already exists — skipping creation")
            return

    es.indices.create(index=ES_INDEX, body=INDEX_MAPPING)
    logger.info(f"✓ Created index '{ES_INDEX}'")


# ── Indexing ──────────────────────────────────────────────────────────────────

def index_products_from_db(es: Elasticsearch, db_engine, batch_size: int = 500) -> int:
    """
    Pull all products from MySQL and bulk-index them into Elasticsearch.
    Returns the total number of documents indexed.
    """
    query = text("""
        SELECT
            asin            AS product_id,
            title           AS product_name,
            stars           AS avg_rating,
            reviews         AS total_reviews,
            price,
            category_id,
            imgUrl          AS img_url,
            productURL      AS product_url
        FROM amazon_products
        WHERE title IS NOT NULL
          AND price > 0
    """)

    def generate_docs(rows):
        for row in rows:
            yield {
                "_index": ES_INDEX,
                "_id"   : row.product_id,
                "_source": {
                    "product_id"   : row.product_id,
                    "product_name" : row.product_name or "",
                    "category_id"  : str(row.category_id or ""),
                    "avg_rating"   : float(row.avg_rating   or 0),
                    "total_reviews": int(row.total_reviews   or 0),
                    "price"        : float(row.price         or 0),
                    "img_url"      : row.img_url      or "",
                    "product_url"  : row.product_url  or "",
                },
            }

    logger.info("📦 Fetching products from DB ...")
    with db_engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    logger.info(f"   → {len(rows):,} products fetched — indexing into ES ...")

    success, failed = helpers.bulk(
        es,
        generate_docs(rows),
        chunk_size=batch_size,
        raise_on_error=False,
        stats_only=True,
    )

    logger.info(f"✓ Indexed {success:,} documents  |  {failed} failures")
    return success


# ── Search ────────────────────────────────────────────────────────────────────

def keyword_search(
    es         : Elasticsearch,
    query      : str,
    top_n      : int            = 10,
    min_rating : float          = 0.0,
    min_price  : Optional[float]= None,
    max_price  : Optional[float]= None,
    category_id: Optional[str]  = None,
    fuzziness  : str            = "AUTO",
) -> list[dict]:
    """
    Full-text keyword search with boosting, fuzzy matching, and optional filters.

    Scoring priority:
        1. Exact phrase match in product_name  (boost ×4)
        2. Individual token match in product_name (boost ×2)
        3. Match in category                   (boost ×1.5)
        4. Fallback to any field

    Args:
        query      : Free-text search string.
        top_n      : Max results to return.
        min_rating : Filter out products below this avg star rating.
        min_price  : Optional lower price bound.
        max_price  : Optional upper price bound.
        category_id: Filter to a specific category ID.
        fuzziness  : ES fuzziness param ('AUTO', '0', '1', '2').

    Returns:
        List of product dicts sorted by relevance score.
    """

    # ── Build filter clauses ──────────────────────────────────────────────────
    filters = [{"range": {"avg_rating": {"gte": min_rating}}}]

    price_range: dict = {}
    if min_price is not None:
        price_range["gte"] = min_price
    if max_price is not None:
        price_range["lte"] = max_price
    if price_range:
        filters.append({"range": {"price": price_range}})

    if category_id:
        filters.append({"term": {"category_id": category_id}})

    # ── Build the query ───────────────────────────────────────────────────────
    es_query = {
        "size": top_n,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query"    : query,
                            "fields"   : [
                                "product_name^4",   # title is most important
                                "category^1.5",
                                "description",
                            ],
                            "type"     : "best_fields",
                            "fuzziness": fuzziness,
                            "operator" : "or",
                        }
                    }
                ],
                "should": [
                    # Reward exact phrase match
                    {
                        "match_phrase": {
                            "product_name": {
                                "query": query,
                                "boost": 4,
                            }
                        }
                    }
                ],
                "filter": filters,
            }
        },
        "_source": [
            "product_id", "product_name", "avg_rating",
            "total_reviews", "price", "category_id",
            "img_url", "product_url",
        ],
    }

    resp = es.search(index=ES_INDEX, body=es_query)
    hits = resp["hits"]["hits"]

    return [
        {
            "product_id"   : h["_source"].get("product_id"),
            "product_name" : h["_source"].get("product_name"),
            "avg_rating"   : h["_source"].get("avg_rating"),
            "total_reviews": h["_source"].get("total_reviews"),
            "price"        : h["_source"].get("price"),
            "category_id"  : h["_source"].get("category_id"),
            "img_url"      : h["_source"].get("img_url"),
            "product_url"  : h["_source"].get("product_url"),
            "score"        : round(h["_score"], 4),
        }
        for h in hits
    ]