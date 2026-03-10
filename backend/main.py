"""
main.py
FastAPI server — Collaborative Filtering, Content-Based Filtering,
Semantic Search (OpenAI + Pinecone), and Elasticsearch keyword search.

"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import pickle
import os
import time
from typing import Optional

from collaborative import (
    build_engine,
    load_model,
    get_recommendations,
    enrich_with_product_details,
)
from content_engine import (
    load_content_model,
    get_content_recommendations,
)
from semantic_search import (
    query_semantic_search,
    get_index_stats,
)
from elastic_search import get_es_client, keyword_search   

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Models Directory ──────────────────────────────────────────────────────────

MODELS_DIR = "models"


# ── App State (loaded once at startup) ───────────────────────────────────────

class AppState:
    engine        = None
    matrix        = None
    sim_matrix    = None
    product_df    = None
    tfidf_matrix  = None
    product_index = None
    es            = None   

state = AppState()


# ── Model Helpers ─────────────────────────────────────────────────────────────

def models_exist() -> bool:
    """Check if all saved model files are present on disk."""
    files = [
        "cf_matrix.pkl", "cf_sim_matrix.pkl",
        "product_df.pkl", "tfidf_matrix.pkl",
        "product_index.pkl", "vectorizer.pkl"
    ]
    return all(os.path.exists(f"{MODELS_DIR}/{f}") for f in files)


# ── Lifespan: Load Models at Startup ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting up ...")

    state.engine = build_engine()

    if models_exist():
        # ── Fast path: load from disk (seconds) ──────────────────────────────
        logger.info("📂 Loading models from disk ...")

        with open(f"{MODELS_DIR}/cf_matrix.pkl",     "rb") as f: state.matrix        = pickle.load(f)
        with open(f"{MODELS_DIR}/cf_sim_matrix.pkl", "rb") as f: state.sim_matrix    = pickle.load(f)
        with open(f"{MODELS_DIR}/product_df.pkl",    "rb") as f: state.product_df    = pickle.load(f)
        with open(f"{MODELS_DIR}/tfidf_matrix.pkl",  "rb") as f: state.tfidf_matrix  = pickle.load(f)
        with open(f"{MODELS_DIR}/product_index.pkl", "rb") as f: state.product_index = pickle.load(f)

        logger.info("✓ Models loaded from disk — startup complete")

    else:
        # ── Slow path: build from DB (first time only) ────────────────────────
        logger.warning("⚠️  No saved models found — building from DB (this will take a few minutes) ...")
        logger.warning("    Run 'python save_models.py' next time to avoid this.")

        state.matrix, state.sim_matrix                               = load_model(state.engine)
        state.product_df, state.tfidf_matrix, state.product_index, _ = load_content_model(state.engine)

        logger.info("✓ Models built and ready")

    # ── Elasticsearch client ──────────────────────────────────────────────────
    try:
        state.es = get_es_client()
        logger.info("✓ Elasticsearch client ready")
    except ConnectionError as e:
        logger.warning(f"⚠️  Elasticsearch unavailable: {e}  — /search/elastic will be disabled")
        state.es = None

    yield

    # Shutdown
    logger.info("Shutting down — disposing DB engine ...")
    state.engine.dispose()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Recommendation Engine API",
    description=(
        "Collaborative Filtering, Content-Based Filtering, "
        "Semantic Search (OpenAI + Pinecone), "
        "and Elasticsearch keyword search endpoints."
    ),
    version="3.0.0",
    lifespan=lifespan,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def validate_user(user_id: int):
    """Raise 404 if user doesn't exist in the rating matrix."""
    if user_id not in state.matrix.index:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} not found in the rating matrix."
        )

def require_es():
    """Raise 503 if Elasticsearch is not available."""
    if state.es is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Elasticsearch is not available. "
                "Start ES and run 'python build_search_index.py', then restart the server."
            ),
        )


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Status"])
def health_check():
    """Check if the API, both recommendation models, and search backends are live."""
    es_ok = False
    if state.es is not None:
        try:
            es_ok = state.es.ping()
        except Exception:
            pass

    return {
        "status"          : "ok",
        "models_from_disk": models_exist(),
        "users_loaded"    : int(state.matrix.shape[0]) if state.matrix      is not None else 0,
        "products_loaded" : int(state.matrix.shape[1]) if state.matrix      is not None else 0,
        "cf_model"        : state.sim_matrix           is not None,
        "content_model"   : state.tfidf_matrix         is not None,
        "elasticsearch"   : es_ok,
    }


# ── Endpoint 1: Sample Users ──────────────────────────────────────────────────

@app.get("/users/sample", tags=["Status"])
def sample_users(
    n: int = Query(default=10, ge=1, le=100, description="Number of sample user IDs to return")
):
    """Returns a sample of user IDs from the matrix — useful for picking test users."""
    sample = state.matrix.index[:n].tolist()
    return {
        "sample_user_ids": sample,
        "total_users"    : len(state.matrix)
    }


# ── Endpoint 2: Collaborative Filtering ──────────────────────────────────────

@app.get("/recommend/collaborative/{user_id}", tags=["Collaborative Filtering"])
def collaborative_recommendations(
    user_id : int,
    top_n   : int  = Query(default=10, ge=1, le=50,  description="Number of recommendations to return"),
    enrich  : bool = Query(default=True,              description="Include full product details"),
):
    """
    Get recommendations using **Collaborative Filtering**.

    - Finds the most similar users based on rating patterns
    - Recommends products those users rated highly that this user hasn't seen
    """
    validate_user(user_id)

    start  = time.time()
    rec_df = get_recommendations(user_id, state.matrix, state.sim_matrix, top_n=top_n)

    if rec_df.empty:
        return JSONResponse(content={"user_id": user_id, "recommendations": [], "count": 0})

    if enrich:
        rec_df = enrich_with_product_details(rec_df, state.engine)

    elapsed = round(time.time() - start, 3)

    return {
        "user_id"        : user_id,
        "method"         : "collaborative_filtering",
        "count"          : len(rec_df),
        "response_time_s": elapsed,
        "recommendations": rec_df.to_dict(orient="records"),
    }


# ── Endpoint 3: Content-Based Filtering ──────────────────────────────────────

@app.get("/recommend/content/{user_id}", tags=["Content-Based Filtering"])
def content_recommendations(
    user_id     : int,
    top_n       : int  = Query(default=10, ge=1, le=50, description="Number of recommendations to return"),
    top_rated_n : int  = Query(default=5,  ge=1, le=20, description="User's top-rated products to use as taste seeds"),
    enrich      : bool = Query(default=True,             description="Include full product details"),
):
    """
    Get recommendations using **Content-Based Filtering** (TF-IDF cosine similarity).

    - Builds a taste profile from the user's highest-rated products
    - Finds unseen products most similar to that taste profile
    """
    validate_user(user_id)

    start  = time.time()
    rec_df = get_content_recommendations(
        user_id,
        state.matrix,
        state.tfidf_matrix,
        state.product_index,
        top_n=top_n,
        top_rated_n=top_rated_n,
    )

    if rec_df.empty:
        return JSONResponse(content={"user_id": user_id, "recommendations": [], "count": 0})

    if enrich:
        rec_df = enrich_with_product_details(rec_df, state.engine)

    elapsed = round(time.time() - start, 3)

    return {
        "user_id"        : user_id,
        "method"         : "content_based_filtering",
        "count"          : len(rec_df),
        "response_time_s": elapsed,
        "recommendations": rec_df.to_dict(orient="records"),
    }


# ── Endpoint 4: Compare Both Side-by-Side ────────────────────────────────────

@app.get("/recommend/compare/{user_id}", tags=["Compare"])
def compare_recommendations(
    user_id : int,
    top_n   : int = Query(default=10, ge=1, le=50, description="Number of recommendations from each method"),
):
    """
    Run **both engines** for the same user and return results side-by-side.
    Useful for directly comparing what each method recommends.
    """
    validate_user(user_id)

    start = time.time()

    cf_df = get_recommendations(user_id, state.matrix, state.sim_matrix, top_n=top_n)
    cb_df = get_content_recommendations(
        user_id, state.matrix, state.tfidf_matrix, state.product_index, top_n=top_n
    )

    if not cf_df.empty:
        cf_df = enrich_with_product_details(cf_df, state.engine)
    if not cb_df.empty:
        cb_df = enrich_with_product_details(cb_df, state.engine)

    cf_ids      = set(cf_df["product_id"]) if not cf_df.empty else set()
    cb_ids      = set(cb_df["product_id"]) if not cb_df.empty else set()
    overlap_ids = cf_ids & cb_ids

    elapsed = round(time.time() - start, 3)

    return {
        "user_id"                : user_id,
        "response_time_s"        : elapsed,
        "overlap_count"          : len(overlap_ids),
        "overlap_product_ids"    : list(overlap_ids),
        "collaborative_filtering": cf_df.to_dict(orient="records") if not cf_df.empty else [],
        "content_based_filtering": cb_df.to_dict(orient="records") if not cb_df.empty else [],
    }


# ── Endpoint 5: Keyword Search (SQL LIKE) ────────────────────────────────────

@app.get("/search", tags=["Search"])
def search_products(
    q          : str   = Query(..., min_length=1,               description="Search term e.g. 'shoes', 'laptop'"),
    top_n      : int   = Query(default=10, ge=1,     le=50,     description="Number of results to return"),
    min_rating : float = Query(default=0.0, ge=0.0,  le=5.0,    description="Minimum average rating filter"),
):
    """
    Search products by title from the database (keyword / LIKE match).
    Results sorted by highest rating first, then by review count.
    """
    try:
        from sqlalchemy import text

        query = """
            SELECT
                asin        AS product_id,
                title       AS product_name,
                stars       AS avg_rating,
                reviews     AS total_reviews,
                price,
                category_id
            FROM amazon_products
            WHERE title LIKE :search_term
              AND stars >= :min_rating
            ORDER BY stars DESC, reviews DESC
            LIMIT :top_n
        """

        with state.engine.connect() as conn:
            rows = conn.execute(text(query), {
                "search_term": f"%{q}%",
                "min_rating" : min_rating,
                "top_n"      : top_n,
            }).fetchall()

        if not rows:
            return {
                "query"  : q,
                "count"  : 0,
                "results": [],
                "message": f"No products found for '{q}'"
            }

        results = [
            {
                "product_id"   : row.product_id,
                "product_name" : row.product_name,
                "avg_rating"   : row.avg_rating,
                "total_reviews": row.total_reviews,
                "price"        : row.price,
                "category_id"  : row.category_id,
            }
            for row in rows
        ]

        return {
            "query"  : q,
            "count"  : len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoint 6: Elasticsearch Keyword Search ─────────────────────────────────

@app.get("/search/elastic", tags=["Search"])
def elastic_search(
    q           : str            = Query(..., min_length=1,             description="Search query e.g. 'wireless headphones'"),
    top_n       : int            = Query(default=10, ge=1,    le=50,    description="Number of results"),
    min_rating  : float          = Query(default=0.0, ge=0.0,  le=5.0, description="Minimum avg star rating"),
    min_price   : Optional[float]= Query(default=None, ge=0,            description="Minimum price filter"),
    max_price   : Optional[float]= Query(default=None, ge=0,            description="Maximum price filter"),
    category_id : Optional[str]  = Query(default=None,                  description="Filter to a specific category ID"),
    fuzziness   : str            = Query(default="AUTO",                description="Typo tolerance: AUTO, 0, 1, 2"),
):
    """
    **Elasticsearch-powered keyword search** — smarter than SQL LIKE.

    Features:
    - **Fuzzy matching** — tolerates typos (`wireles headphon` → wireless headphones)
    - **Relevance scoring** — title matches rank higher than category matches
    - **Phrase boost** — exact phrase matches float to the top
    - **Filters** — price range, min rating, category
    - Returns a `score` field per result showing match strength

    **Setup required (once):**
    ```
    python build_search_index.py
    ```
    """
    require_es()

    start = time.time()

    try:
        results = keyword_search(
            es          = state.es,
            query       = q,
            top_n       = top_n,
            min_rating  = min_rating,
            min_price   = min_price,
            max_price   = max_price,
            category_id = category_id,
            fuzziness   = fuzziness,
        )
    except Exception as e:
        logger.error(f"Elasticsearch search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if not results:
        return {
            "query"          : q,
            "method"         : "elasticsearch",
            "count"          : 0,
            "results"        : [],
            "response_time_s": round(time.time() - start, 3),
            "message"        : f"No products found for '{q}'",
        }

    return {
        "query"          : q,
        "method"         : "elasticsearch",
        "count"          : len(results),
        "response_time_s": round(time.time() - start, 3),
        "results"        : results,
    }


# ── Endpoint 7: Semantic Search (OpenAI + Pinecone) ───────────────────────────

@app.get("/search/semantic", tags=["Search"])
def semantic_search(
    q           : str            = Query(..., min_length=1,            description="Natural language query e.g. 'comfortable running shoes for wide feet'"),
    top_n       : int            = Query(default=10, ge=1,   le=50,    description="Number of results to return"),
    min_rating  : float          = Query(default=0.0, ge=0.0, le=5.0,  description="Minimum average rating filter"),
    max_price   : Optional[float]= Query(default=None, ge=0.0,         description="Maximum price filter"),
    category_id : Optional[str]  = Query(default=None,                 description="Filter by category ID"),
):
    """
    **Semantic Search** powered by OpenAI Embeddings + Pinecone.

    Unlike keyword search, this understands *meaning* — so:
    - "noise cancelling headphones" matches "headphones with active noise reduction"
    - "gift for a 5 year old" matches children's toys and games
    - "budget laptop for students" matches affordable student-friendly laptops

    Each result includes a `similarity_score` (0–1, higher = more relevant).

    **Setup required (once):**
    ```
    python semantic_search.py --index
    ```
    """
    start = time.time()

    try:
        results = query_semantic_search(
            query       = q,
            top_n       = top_n,
            min_rating  = min_rating,
            max_price   = max_price,
            category_id = category_id,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = round(time.time() - start, 3)

    if not results:
        return {
            "query"          : q,
            "method"         : "semantic_search",
            "count"          : 0,
            "results"        : [],
            "response_time_s": elapsed,
            "message"        : f"No products found for '{q}' — ensure the index has been built.",
        }

    return {
        "query"          : q,
        "method"         : "semantic_search",
        "count"          : len(results),
        "response_time_s": elapsed,
        "results"        : results,
    }


# ── Endpoint 8: Semantic Index Stats ─────────────────────────────────────────

@app.get("/search/semantic/stats", tags=["Search"])
def semantic_index_stats():
    """
    Returns stats about the Pinecone semantic index
    (total vectors indexed, model used, dimensions).
    """
    try:
        return get_index_stats()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Pinecone stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoint 9: Homepage Paginated Products ───────────────────────────────────

@app.get("/products/homepage", tags=["Homepage"])
def homepage_products(
    page     : int = Query(default=1,  ge=1,         description="Page number (starts at 1)"),
    per_page : int = Query(default=25, ge=1, le=100, description="Products per page (default 25)"),
    sort_by  : str = Query(default="alphabetical",   description="Sort: 'alphabetical', 'rating', 'price_asc', 'price_desc'"),
):
    """
    Homepage product listing with pagination.
    Returns 25 products per page sorted alphabetically by default.
    Includes next/previous page navigation.
    """
    sort_map = {
        "alphabetical": "title ASC",
        "rating"      : "stars DESC, reviews DESC",
        "price_asc"   : "price ASC",
        "price_desc"  : "price DESC",
    }

    if sort_by not in sort_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by. Choose from: {list(sort_map.keys())}"
        )

    order_clause = sort_map[sort_by]
    offset       = (page - 1) * per_page

    try:
        from sqlalchemy import text

        with state.engine.connect() as conn:
            total_products = conn.execute(text(
                "SELECT COUNT(*) FROM amazon_products WHERE title IS NOT NULL AND price > 0"
            )).scalar()

        query = f"""
            SELECT
                asin        AS product_id,
                title       AS product_name,
                stars       AS avg_rating,
                reviews     AS total_reviews,
                price,
                category_id
            FROM amazon_products
            WHERE title IS NOT NULL
              AND price > 0
            ORDER BY {order_clause}
            LIMIT :per_page OFFSET :offset
        """

        with state.engine.connect() as conn:
            rows = conn.execute(text(query), {
                "per_page": per_page,
                "offset"  : offset,
            }).fetchall()

        total_pages  = -(-total_products // per_page)   # ceiling division
        has_next     = page < total_pages
        has_previous = page > 1

        products = [
            {
                "product_id"   : row.product_id,
                "product_name" : row.product_name,
                "avg_rating"   : row.avg_rating,
                "total_reviews": row.total_reviews,
                "price"        : row.price,
                "category_id"  : row.category_id,
            }
            for row in rows
        ]

        return {
            "products"  : products,
            "pagination": {
                "current_page"  : page,
                "per_page"      : per_page,
                "total_pages"   : total_pages,
                "total_products": total_products,
                "has_next"      : has_next,
                "has_previous"  : has_previous,
                "next_page"     : page + 1 if has_next     else None,
                "previous_page" : page - 1 if has_previous else None,
            },
            "links": {
                "current" : f"/products/homepage?page={page}&per_page={per_page}&sort_by={sort_by}",
                "next"    : f"/products/homepage?page={page + 1}&per_page={per_page}&sort_by={sort_by}" if has_next     else None,
                "previous": f"/products/homepage?page={page - 1}&per_page={per_page}&sort_by={sort_by}" if has_previous else None,
                "first"   : f"/products/homepage?page=1&per_page={per_page}&sort_by={sort_by}",
                "last"    : f"/products/homepage?page={total_pages}&per_page={per_page}&sort_by={sort_by}",
            },
        }

    except Exception as e:
        logger.error(f"Homepage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))