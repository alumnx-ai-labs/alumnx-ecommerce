"""
FastAPI Amazon Product API

Endpoints:
  GET  /health                                           → API + DB status
  GET  /products                                         → Paginated product list
  GET  /products/search                                  → Semantic search via AI service
  GET  /products/{asin}                                  → Single product
  POST /products                                         → Create product
  PUT  /products/{asin}                                  → Update product
  DELETE /products/{asin}                                → Delete product
  GET  /categories                                       → All categories
  GET  /users/{user_id}/profile                          → User info + ratings
  GET  /stats                                            → Overall system stats
  GET  /users/{user_id}/recommendations/collaborative    → Collaborative filtering
  GET  /users/{user_id}/recommendations/content-based   → TF-IDF content filtering
  GET  /users/{user_id}/recommendations/hybrid          → Hybrid (CF + TF-IDF)
"""

import os
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from dotenv import load_dotenv
import pandas as pd
import logging
from datetime import datetime
import httpx
from typing import Dict

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# ── Global State ───────────────────────────────────────────────────────────────
state = {
    "engine": None,
    "ready":  False,
}

# ── Configuration ──────────────────────────────────────────────────────────────
DB_HOST        = os.getenv("DB_HOST")
DB_PORT        = int(os.getenv("DB_PORT", 3306))
DB_NAME        = os.getenv("DB_NAME")
DB_USER        = os.getenv("DB_USER")
DB_PASSWORD    = os.getenv("DB_PASSWORD")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://0.0.0.0:8006")

# ── Helper: Run SQL and return DataFrame ───────────────────────────────────────

def query_db(sql: str, params: dict = {}) -> pd.DataFrame:
    with state["engine"].connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)

def build_engine():
    from sqlalchemy import create_engine
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url, pool_pre_ping=True)

# ── Lifespan: connect DB on startup, dispose on shutdown ──────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting up API from {os.path.abspath(__file__)} ...")
    engine = build_engine()

    def _ping():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    await asyncio.to_thread(_ping)
    logger.info("✓ Connected to RDS")
    state["engine"] = engine
    state["ready"]  = True

    # Fire both cache warmers concurrently in background threads.
    # asyncio.to_thread → runs the blocking DB/CPU work in a thread pool
    # without blocking the event loop, so the server accepts requests immediately.
    async def _warm_background():
        try:
            await asyncio.gather(
                asyncio.to_thread(_warm_tfidf_cache),
                asyncio.to_thread(_warm_cf_cache),
            )
            logger.info("✓ Background cache warm-up complete")
        except Exception as e:
            logger.warning(f"Background cache warm-up error: {e}")

    asyncio.create_task(_warm_background())
    logger.info("✓ API ready — cache warming in background")
    yield
    if state["engine"]:
        state["engine"].dispose()
        logger.info("✓ DB connection pool closed")

# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Amazon Product API",
    description="Core Product, User, and Recommendation API.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory TTL cache ────────────────────────────────────────────────────────
# Avoids rebuilding heavy matrices (TF-IDF, interaction matrix, cosine similarity)
# on every request. Each cache entry is invalidated after CACHE_TTL seconds.
_CACHE_TTL = 600  # 10 minutes

_tfidf_cache: dict = {"ts": 0, "tfidf_matrix": None, "asin_to_idx": None, "all_products_df": None}
_cf_cache:    dict = {"ts": 0, "pivot": None, "ratings_matrix": None, "user_similarity": None}


def _tfidf_cache_valid() -> bool:
    return _tfidf_cache["tfidf_matrix"] is not None and (time.time() - _tfidf_cache["ts"]) < _CACHE_TTL

def _cf_cache_valid() -> bool:
    return _cf_cache["pivot"] is not None and (time.time() - _cf_cache["ts"]) < _CACHE_TTL


def _warm_tfidf_cache():
    """Build and store the TF-IDF matrix. Called once at startup."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    logger.info("Pre-warming TF-IDF cache...")
    df = query_db(
        "SELECT asin, title FROM amazon_products "
        "WHERE title IS NOT NULL AND title != '' "
        "ORDER BY stars DESC, reviews DESC "
        "LIMIT 15000"
    )
    if df.empty:
        logger.warning("TF-IDF pre-warm skipped — no products in DB")
        return
    vectorizer   = TfidfVectorizer(stop_words="english", max_features=5000, ngram_range=(1, 2))
    tfidf_matrix = vectorizer.fit_transform(df["title"].fillna(""))
    asin_to_idx  = {asin: i for i, asin in enumerate(df["asin"])}
    _tfidf_cache["all_products_df"] = df
    _tfidf_cache["tfidf_matrix"]    = tfidf_matrix
    _tfidf_cache["asin_to_idx"]     = asin_to_idx
    _tfidf_cache["ts"]              = time.time()
    logger.info(f"✓ TF-IDF cache ready ({len(df):,} products)")


def _warm_cf_cache():
    """Build and store the interaction matrix + cosine similarity. Called once at startup."""
    import numpy as np
    logger.info("Pre-warming CF cache...")
    ratings_df = query_db(
        "SELECT user_id, product_id, rating FROM product_ratings "
        "ORDER BY rating DESC LIMIT 20000"
    )
    if ratings_df.empty:
        logger.warning("CF pre-warm skipped — no ratings in DB")
        return
    pivot          = ratings_df.pivot_table(index="user_id", columns="product_id", values="rating", fill_value=0)
    ratings_matrix = pivot.to_numpy()
    norms          = np.linalg.norm(ratings_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    normalised     = ratings_matrix / norms
    user_similarity = np.dot(normalised, normalised.T)
    _cf_cache["pivot"]           = pivot
    _cf_cache["ratings_matrix"]  = ratings_matrix
    _cf_cache["user_similarity"] = user_similarity
    _cf_cache["ts"]              = time.time()
    logger.info(f"✓ CF cache ready ({pivot.shape[0]} users × {pivot.shape[1]} products)")


# ══════════════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["General"])
def health_check():
    """Check if API and DB are running."""
    try:
        with state["engine"].connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status":      "ok",
            "db_connected": True,
            "timestamp":   datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. PRODUCTS (CRUD)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/products", tags=["Products"])
def get_products(
    page:  int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    category_id: int = Query(default=None),
):
    """List products with pagination and optional category filter."""
    offset = (page - 1) * limit
    where_clause = ""
    params = {"limit": limit, "offset": offset}
    
    if category_id:
        where_clause = "WHERE category_id = :cat_id"
        params["cat_id"] = category_id

    # DB columns are camelCase: imgUrl, productURL
    sql = f"""
        SELECT 
            asin, title, stars, reviews, price, category_id,
            imgUrl, productURL
        FROM amazon_products 
        {where_clause} 
        LIMIT :limit OFFSET :offset
    """
    try:
        with state["engine"].connect() as conn:
            # 1. Get total count for pagination
            count_sql = f"SELECT COUNT(*) FROM amazon_products {where_clause}"
            total_total = conn.execute(text(count_sql), params).scalar()
            
            # 2. Get the products for the current page
            logger.info(f"Querying products: {sql} with params {params}")
            df = pd.read_sql(text(sql), conn, params=params)
            logger.info(f"Query returned {len(df)} rows")
            
        return {
            "page": page,
            "limit": limit,
            "total_count": total_total,
            "total_pages": (total_total + limit - 1) // limit,
            "products": df.fillna("N/A").to_dict(orient="records")
        }
    except Exception as e:
        logger.error(f"Products query failed: {e}")
        return {"page": page, "limit": limit, "total_results": 0, "products": []}

@app.get("/products/search", tags=["Products"])
def search_products(query: str = Query(...), limit: int = Query(default=15, le=50)):
    """
    Semantic Search:
    1. Send query to AI Service.
    2. Get ASINs from Pinecone results.
    3. Fetch full product details from DB.
    """
    try:
        # A. Get IDs from AI Service
        res = httpx.get(f"{AI_SERVICE_URL}/search", params={"query": query, "top_k": limit}, timeout=10.0)
        res.raise_for_status()
        search_data = res.json()
        matches = search_data.get("matches", [])
        
        # 0.5 Cutoff: Only keep results that are truly semantically relevant
        RELEVANCE_THRESHOLD = 0.5
        filtered_matches = [m for m in matches if m.get("score", 0) >= RELEVANCE_THRESHOLD]
        asins = [m["product_id"] for m in filtered_matches]
        
        if not asins:
            logger.info(f"No results passed the relevance threshold (0.5) for query: {query}")
            return {"query": query, "total_results": 0, "products": [], "message": "No highly relevant matches found"}

        # B. Fetch details from DB (preserve order)
        placeholders = ", ".join([f":asin_{i}" for i in range(len(asins))])
        params = {f"asin_{i}": asin for i, asin in enumerate(asins)}
        
        sql = f"""
            SELECT * FROM amazon_products 
            WHERE asin IN ({placeholders})
            ORDER BY FIELD(asin, {placeholders})
        """
        sql_final = text(sql)
        
        with state["engine"].connect() as conn:
            df = pd.read_sql(sql_final, conn, params=params)
            
        return {
            "query": query,
            "total_results": len(df),
            "products": df.fillna("N/A").to_dict(orient="records")
        }
        
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/{asin}", tags=["Products"])
def get_product(asin: str):
    """Get a single product by ASIN."""
    sql = "SELECT * FROM amazon_products WHERE asin = :asin"
    df = query_db(sql, {"asin": asin})
    if df.empty:
        raise HTTPException(status_code=404, detail="Product not found")
    return df.fillna("N/A").to_dict(orient="records")[0]

@app.post("/products", tags=["Products"])
def create_product(product: dict):
    """Create a new product."""
    required = ["asin", "title", "category_id"]
    for field in required:
        if field not in product:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
            
    try:
        with state["engine"].begin() as conn:
            # Dynamically build the insert using keys directly
            cols = ", ".join(product.keys())
            placeholders = ", ".join([f":{k}" for k in product.keys()])
            sql = text(f"INSERT INTO amazon_products ({cols}) VALUES ({placeholders})")
            conn.execute(sql, product)
        
        # Trigger sync to AI Service
        try:
            # We use 'title' as the description if no specific description field exists
            sync_payload = {
                "product_id": product["asin"],
                "description": product.get("title", "")
            }
            httpx.post(f"{AI_SERVICE_URL}/embed-description", json=sync_payload, timeout=10.0)
            logger.info(f"Triggered Pinecone embedding sync for {product['asin']}")
        except Exception as e:
            logger.warning(f"Failed to trigger AI Service sync: {e}")

        return {"message": "Product created successfully", "asin": product["asin"]}
    except Exception as e:
        logger.error(f"Create product failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/products/{asin}", tags=["Products"])
def update_product(asin: str, product: dict):
    """Update an existing product."""
    params = {**product}
    if "asin" in params:
        del params["asin"]

    try:
        with state["engine"].begin() as conn:
            updates = ", ".join([f"{k} = :{k}" for k in params.keys()])
            sql = text(f"UPDATE amazon_products SET {updates} WHERE asin = :target_asin")
            conn.execute(sql, {**params, "target_asin": asin})
        
        # Sync updated product
        try:
            sync_payload = {
                "product_id": asin,
                "description": params.get("title", "")
            }
            if sync_payload["description"]: # only sync if we have a title to embed
                httpx.post(f"{AI_SERVICE_URL}/embed-description", json=sync_payload, timeout=10.0)
                logger.info(f"Triggered Pinecone embedding sync for {asin}")
        except Exception as e:
            logger.warning(f"Failed to trigger AI Service sync: {e}")

        return {"message": "Product updated successfully"}
    except Exception as e:
        logger.error(f"Update product failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/products/{asin}", tags=["Products"])
def delete_product(asin: str):
    """Delete a product."""
    try:
        with state["engine"].begin() as conn:
            conn.execute(text("DELETE FROM amazon_products WHERE asin = :asin"), {"asin": asin})
        return {"message": "Product deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 3. CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/categories", tags=["General"])
def get_categories():
    """List all categories."""
    df = query_db("SELECT * FROM amazon_categories ORDER BY category_name")
    return df.to_dict(orient="records")


# ══════════════════════════════════════════════════════════════════════════════
# 4. USER PROFILE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/users/{user_id}/profile", tags=["Users"])
def get_user_profile(user_id: int):
    """
    Full user profile:
    - User info (name, age group, country)
    - Products they have rated
    """
    user_df = query_db("SELECT * FROM users WHERE user_id = :uid", {"uid": user_id})
    if user_df.empty:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    ratings_df = query_db("""
        SELECT
            r.product_id,
            r.rating,
            r.rated_at,
            p.title   AS product_name,
            p.price,
            c.category_name
        FROM product_ratings r
        LEFT JOIN amazon_products   p ON r.product_id  = p.asin
        LEFT JOIN amazon_categories c ON p.category_id = c.id
        WHERE r.user_id = :uid
        ORDER BY r.rating DESC
        LIMIT 500
    """, {"uid": user_id})

    return {
        "user":                  user_df.fillna("N/A").to_dict(orient="records")[0],
        "total_ratings":         len(ratings_df),
        "ratings":               ratings_df.fillna("N/A").to_dict(orient="records"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. OVERALL STATS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/stats", tags=["General"])
def get_stats():
    """High-level stats about the system."""
    stats = {}

    queries = {
        "total_users":           "SELECT COUNT(*) FROM users",
        "total_products":        "SELECT COUNT(*) FROM amazon_products",
        "total_categories":      "SELECT COUNT(*) FROM amazon_categories",
        "total_ratings":         "SELECT COUNT(*) FROM product_ratings",
    }

    with state["engine"].connect() as conn:
        for key, sql in queries.items():
            result = conn.execute(text(sql)).scalar()
            stats[key] = float(result) if result is not None else 0

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# 6. COLLABORATIVE FILTERING
# ══════════════════════════════════════════════════════════════════════════════

def _run_collaborative_filtering(user_id: int, top_k: int, k_similar_users: int = 10) -> list:
    """
    User-Based Collaborative Filtering with Cosine Similarity.

    "Find users who rated products the same way as you, then recommend
     what THEY liked but YOU haven't seen yet."

    This directly mirrors the notebook approach:
        CollaborativeFiltering.ipynb  →  Tasks 4 – 7

    Step-by-step:
    ┌─────────────────────────────────────────────────────────────────┐
    │ 1. Load ALL ratings from DB                                     │
    │                                                                 │
    │ 2. Build a User × Product interaction matrix (pivot table).     │
    │    Rows = users, Columns = product ASINs, Values = ratings.     │
    │    Unrated products → 0.                                        │
    │                                                                 │
    │    e.g.            P001  P002  P003  P004                       │
    │         user_1  [  5     3     0     0  ]                       │
    │         user_2  [  4     0     5     0  ]                       │
    │         user_3  [  0     0     4     5  ]  ← target             │
    │                                                                 │
    │ 3. Compute cosine similarity between every pair of user rows.   │
    │    Two users are "similar" if the angle between their rating    │
    │    vectors is small (they point in the same direction).         │
    │                                                                 │
    │         similarity[i][j] = (row_i · row_j) / (|row_i| |row_j|) │
    │                                                                 │
    │ 4. For the target user, sort all other users by similarity      │
    │    score (descending) and pick the top-k neighbours.            │
    │                                                                 │
    │ 5. Average the k neighbours' ratings column-by-column           │
    │    → "predicted score" for every product.                       │
    │                                                                 │
    │ 6. Zero out products the target user already rated.             │
    │                                                                 │
    │ 7. Sort remaining products by predicted score → return top-k.   │
    └─────────────────────────────────────────────────────────────────┘
    """
    import numpy as np

    # ── Steps 1-3: Load ratings + build matrices (cached for 10 min) ──
    if _cf_cache_valid():
        pivot          = _cf_cache["pivot"]
        ratings_matrix = _cf_cache["ratings_matrix"]
        user_similarity = _cf_cache["user_similarity"]
        logger.info("CF: using cached interaction matrix")
    else:
        logger.info("CF: building interaction matrix from DB...")
        ratings_df = query_db(
            "SELECT user_id, product_id, rating FROM product_ratings "
            "ORDER BY rating DESC LIMIT 20000"
        )

        if ratings_df.empty:
            return []

        # Step 2: Build User × Product interaction matrix
        # Matches notebook Task 4: ratings.pivot_table(index="user_id", ...)
        pivot = ratings_df.pivot_table(
            index="user_id",
            columns="product_id",
            values="rating",
            fill_value=0,
        )
        ratings_matrix = pivot.to_numpy()   # shape: (n_users, n_products)

        # Step 3: Cosine similarity between all user rows
        # Matches notebook Task 6: cosine_similarity(ratings_matrix)
        norms = np.linalg.norm(ratings_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1e-9
        normalised      = ratings_matrix / norms
        user_similarity = np.dot(normalised, normalised.T)  # (n_users, n_users)

        _cf_cache["pivot"]          = pivot
        _cf_cache["ratings_matrix"] = ratings_matrix
        _cf_cache["user_similarity"] = user_similarity
        _cf_cache["ts"]             = time.time()
        logger.info("CF: matrix cached")

    if user_id not in pivot.index:
        logger.info(f"CF: user {user_id} has no ratings; returning empty list.")
        return []

    # Map user_id → row index in the matrix
    user_index = pivot.index.get_loc(user_id)

    # ── Step 4: Find k most similar users ────────────────────────────
    # Matches notebook Task 7: np.argsort(similarity_scores)[::-1][1:k+1]
    similarity_scores = user_similarity[user_index]
    similar_user_indices = np.argsort(similarity_scores)[::-1][1 : k_similar_users + 1]

    # ── Step 5: Average the similar users' ratings ───────────────────
    # Matches notebook: avg_movie_ratings = ratings_matrix[similar_users].mean(axis=0)
    avg_ratings = ratings_matrix[similar_user_indices].mean(axis=0)  # (n_products,)

    # ── Step 6: Zero out products the user already rated ─────────────
    # Matches notebook: avg_movie_ratings[ratings_matrix[user_index] > 0] = 0
    avg_ratings[ratings_matrix[user_index] > 0] = 0

    # ── Step 7: Return top-k unrated products ─────────────────────────
    # Matches notebook: top_movie_indices = np.argsort(avg_movie_ratings)[::-1][:top_n]
    top_indices = np.argsort(avg_ratings)[::-1][:top_k]
    top_asins   = pivot.columns[top_indices].tolist()
    top_scores  = avg_ratings[top_indices].tolist()

    return [
        {"asin": asin, "predicted_rating": round(float(score), 3)}
        for asin, score in zip(top_asins, top_scores)
        if score > 0   # only include products with a positive predicted score
    ]


@app.get("/users/{user_id}/recommendations/collaborative", tags=["Recommendations"])
def collaborative_recommendations(
    user_id: int,
    top_k: int = Query(default=10, ge=1, le=50),
):
    """
    Collaborative Filtering Recommendations.

    Finds users with similar rating patterns (cosine similarity), averages
    their ratings, and recommends unrated products with the highest
    predicted score for this user.
    """
    try:
        cf_results = _run_collaborative_filtering(user_id, top_k)

        if not cf_results:
            popular_df = query_db(
                "SELECT * FROM amazon_products "
                "WHERE stars IS NOT NULL AND reviews IS NOT NULL "
                "ORDER BY stars DESC, reviews DESC LIMIT :lim",
                {"lim": top_k},
            )
            return {
                "user_id": user_id,
                "method": "popular",
                "total": len(popular_df),
                "products": popular_df.fillna("N/A").to_dict(orient="records"),
            }

        # Fetch full product details for the recommended ASINs
        asins = [r["asin"] for r in cf_results]
        score_map = {r["asin"]: r["predicted_rating"] for r in cf_results}

        placeholders = ", ".join([f":a{i}" for i in range(len(asins))])
        params = {f"a{i}": a for i, a in enumerate(asins)}
        sql = text(
            f"SELECT * FROM amazon_products WHERE asin IN ({placeholders})"
        )

        with state["engine"].connect() as conn:
            df = pd.read_sql(sql, conn, params=params)

        products = df.fillna("N/A").to_dict(orient="records")
        for p in products:
            p["predicted_rating"] = score_map.get(p["asin"], 0.0)

        # Sort to preserve CF ranking order
        products.sort(key=lambda p: p["predicted_rating"], reverse=True)

        return {
            "user_id": user_id,
            "method": "collaborative",
            "total": len(products),
            "products": products,
        }

    except Exception as exc:
        logger.error(f"Collaborative filtering error for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# 7. CONTENT-BASED FILTERING  (TF-IDF + Cosine Similarity)
# ══════════════════════════════════════════════════════════════════════════════

def _run_content_based_tfidf(
    user_id: int,
    top_k: int = 10,
    rating_threshold: float = 4.0,
) -> list:
    """
    Content-Based Filtering using TF-IDF + Cosine Similarity.

    "If you liked product A, here are products with SIMILAR TITLES to A."

    ┌────────────────────────────────────────────────────────────────────┐
    │  What is TF-IDF?                                                   │
    │                                                                    │
    │  TF  = Term Frequency  → how often a word appears in ONE product   │
    │        title (normalised by title length).                         │
    │  IDF = Inverse Document Frequency → log(total_products /          │
    │        products_containing_that_word).                             │
    │        Rare words get a HIGH IDF; common words ("the", "for")     │
    │        get a LOW IDF and are effectively ignored.                  │
    │                                                                    │
    │  TF-IDF(word, title) = TF × IDF                                   │
    │  → high score for words that are frequent in THIS title but       │
    │    rare across ALL titles  (i.e., truly distinguishing words).    │
    │                                                                    │
    │  Each product title becomes a VECTOR in vocabulary space.          │
    │  We then use COSINE SIMILARITY to find which vectors point in      │
    │  the same direction (→ talk about the same things).               │
    └────────────────────────────────────────────────────────────────────┘

    Step-by-step algorithm:
    1. Load ALL product titles from amazon_products (our database).
    2. Build a TF-IDF matrix: each product → a row vector of TF-IDF weights.
       Shape: (n_products, vocabulary_size).
    3. Get the user's seed products (rating >= threshold).
    4. For each seed product:
         a. Look up its TF-IDF row vector.
         b. Compute cosine similarity vs EVERY other product.
         c. Weight the similarity by the user's rating for that seed
            (a 5-star seed matters more than a 4-star seed).
    5. Accumulate weighted scores across all seeds.
    6. Filter out products the user already rated.
    7. Sort by accumulated score → return top-k.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    # ── Step 1: Load user's rated products (always fresh — user-specific) ─
    ratings_df = query_db(
        """
        SELECT r.product_id AS asin, r.rating, p.title
        FROM   product_ratings r
        LEFT JOIN amazon_products p ON r.product_id = p.asin
        WHERE  r.user_id = :uid
        """,
        {"uid": user_id},
    )

    if ratings_df.empty:
        return []

    # ── Steps 2-3: Load products + build TF-IDF matrix (cached for 10 min) ─
    if _tfidf_cache_valid():
        all_products_df = _tfidf_cache["all_products_df"]
        tfidf_matrix    = _tfidf_cache["tfidf_matrix"]
        asin_to_idx     = _tfidf_cache["asin_to_idx"]
        logger.info("CB: using cached TF-IDF matrix")
    else:
        logger.info("CB: building TF-IDF matrix from DB...")
        all_products_df = query_db(
            "SELECT asin, title FROM amazon_products "
            "WHERE title IS NOT NULL AND title != '' "
            "ORDER BY stars DESC, reviews DESC "
            "LIMIT 15000"
        )

        if all_products_df.empty:
            return []

        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(all_products_df["title"].fillna(""))
        asin_to_idx  = {asin: i for i, asin in enumerate(all_products_df["asin"])}

        _tfidf_cache["all_products_df"] = all_products_df
        _tfidf_cache["tfidf_matrix"]    = tfidf_matrix
        _tfidf_cache["asin_to_idx"]     = asin_to_idx
        _tfidf_cache["ts"]              = time.time()
        logger.info("CB: TF-IDF matrix cached")

    # ── Step 4: Identify seed products ───────────────────────────────
    already_seen: set = set(ratings_df["asin"].tolist())

    seed_df = ratings_df[ratings_df["rating"] >= rating_threshold]
    if seed_df.empty:
        # Fallback: top-3 rated items if nothing clears the threshold
        seed_df = ratings_df.nlargest(3, "rating")

    # ── Step 5: Compute TF-IDF cosine similarity for each seed ───────
    aggregated_scores: dict = {}
    asin_to_reason: dict = {}

    for _, row in seed_df.iterrows():
        seed_asin  = row["asin"]
        seed_title = str(row.get("title", "")).strip()
        seed_rating = float(row["rating"])

        if seed_asin not in asin_to_idx or not seed_title:
            continue

        seed_idx    = asin_to_idx[seed_asin]
        seed_vector = tfidf_matrix[seed_idx]   # sparse (1, n_features) row

        # cosine_similarity returns a (1, n_products) array
        similarities = cosine_similarity(seed_vector, tfidf_matrix).flatten()

        # Weight: higher-rated seeds contribute more to the accumulated score
        weight = seed_rating / 5.0   # → [0, 1]

        for i, sim_score in enumerate(similarities):
            candidate_asin = all_products_df.iloc[i]["asin"]

            if candidate_asin in already_seen:
                continue
            if sim_score <= 0:
                continue

            weighted = float(sim_score) * weight
            aggregated_scores[candidate_asin] = (
                aggregated_scores.get(candidate_asin, 0.0) + weighted
            )

            if candidate_asin not in asin_to_reason:
                snippet = seed_title[:50] + ("…" if len(seed_title) > 50 else "")
                asin_to_reason[candidate_asin] = f'Similar to "{snippet}"'

    # ── Step 6: Sort and return top-k ────────────────────────────────
    ranked = sorted(aggregated_scores.items(), key=lambda x: x[1], reverse=True)

    return [
        {
            "asin":   asin,
            "score":  round(score, 4),
            "reason": asin_to_reason.get(asin, "Similar to your liked products"),
        }
        for asin, score in ranked[:top_k]
    ]


@app.get("/users/{user_id}/recommendations/content-based", tags=["Recommendations"])
def content_based_recommendations(
    user_id: int,
    top_k: int = Query(default=10, ge=1, le=50),
):
    """
    Content-Based Filtering Recommendations using TF-IDF + Cosine Similarity.

    Builds a TF-IDF matrix from all product titles in our database, then
    finds products whose titles are most similar to what the user has liked.
    No external services required — runs entirely on our product data.
    """
    try:
        cb_results = _run_content_based_tfidf(user_id, top_k)

        if not cb_results:
            return {"user_id": user_id, "method": "content_based", "products": []}

        asins      = [r["asin"] for r in cb_results]
        score_map  = {r["asin"]: r["score"]  for r in cb_results}
        reason_map = {r["asin"]: r["reason"] for r in cb_results}

        placeholders = ", ".join([f":a{i}" for i in range(len(asins))])
        params = {f"a{i}": a for i, a in enumerate(asins)}
        sql = text(f"SELECT * FROM amazon_products WHERE asin IN ({placeholders})")

        with state["engine"].connect() as conn:
            df = pd.read_sql(sql, conn, params=params)

        products = df.fillna("N/A").to_dict(orient="records")
        for p in products:
            p["similarity_score"] = score_map.get(p["asin"], 0.0)
            p["reason"]           = reason_map.get(p["asin"], "")

        products.sort(key=lambda p: p["similarity_score"], reverse=True)

        return {
            "user_id": user_id,
            "method":  "content_based",
            "total":   len(products),
            "products": products,
        }

    except Exception as exc:
        logger.error(f"Content-based filtering error for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# 8. HYBRID RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/users/{user_id}/recommendations/hybrid", tags=["Recommendations"])
def hybrid_recommendations(
    user_id: int,
    top_k: int = Query(default=10, ge=1, le=50),
    cf_weight: float = Query(default=0.5, ge=0.0, le=1.0,
                             description="Weight for CF score (0=pure CB, 1=pure CF)"),
):
    """
    Hybrid Recommendations = Collaborative Filtering + Content-Based Filtering (TF-IDF).

    Combines both signals:
      hybrid_score = cf_weight * CF_score + (1 - cf_weight) * CB_score

    Both scores are normalised to [0, 1] before combining so they are
    comparable regardless of their original scales.

    Products that appear in BOTH lists get a strong boost; products that
    only appear in one list are also considered.
    """
    # 1. Quick check: does user have any ratings?
    ratings_df = query_db(
        "SELECT COUNT(*) AS cnt FROM product_ratings WHERE user_id = :uid",
        {"uid": user_id},
    )
    if ratings_df.empty or ratings_df.iloc[0]["cnt"] == 0:
        # No ratings yet — return top-rated popular products as a cold-start fallback
        popular_df = query_db(
            "SELECT * FROM amazon_products "
            "WHERE stars IS NOT NULL AND reviews IS NOT NULL "
            "ORDER BY stars DESC, reviews DESC "
            "LIMIT :lim",
            {"lim": top_k},
        )
        products = popular_df.fillna("N/A").to_dict(orient="records")
        return {
            "user_id":  user_id,
            "method":   "popular",
            "total":    len(products),
            "products": products,
        }

    # 2. Run CF (user-based cosine similarity, in-process)
    cf_results = _run_collaborative_filtering(user_id, top_k * 2)

    # 3. Run CB (TF-IDF cosine similarity, in-process — no external service needed)
    cb_recommendations = []
    try:
        cb_recommendations = _run_content_based_tfidf(user_id, top_k * 2)
    except Exception as exc:
        logger.warning(f"Hybrid: TF-IDF CB failed, using CF only. Error: {exc}")

    # 4. Normalise CF scores to [0, 1]
    # CF predicted_rating is typically in [1, 5].  Clamp then scale.
    cf_score_map: Dict[str, float] = {}
    if cf_results:
        raw_scores = [r["predicted_rating"] for r in cf_results]
        min_s, max_s = min(raw_scores), max(raw_scores)
        denom = max(max_s - min_s, 1e-9)
        cf_score_map = {
            r["asin"]: (r["predicted_rating"] - min_s) / denom
            for r in cf_results
        }

    # 5. CB scores are already cosine similarities ∈ [0, 1] (normalised)
    cb_score_map: Dict[str, float]   = {r["asin"]: r["score"] for r in cb_recommendations}
    cb_reason_map: Dict[str, str]    = {r["asin"]: r.get("reason", "") for r in cb_recommendations}

    # 6. Union of all candidate ASINs
    all_asins = set(cf_score_map.keys()) | set(cb_score_map.keys())

    # 7. Compute hybrid score for each candidate
    scored: list = []
    for asin in all_asins:
        cf_s = cf_score_map.get(asin, 0.0)
        cb_s = cb_score_map.get(asin, 0.0)
        hybrid_s = cf_weight * cf_s + (1.0 - cf_weight) * cb_s

        sources = []
        if asin in cf_score_map:
            sources.append("collaborative")
        if asin in cb_score_map:
            sources.append("content_based")

        scored.append({
            "asin":          asin,
            "hybrid_score":  round(hybrid_s, 4),
            "cf_score":      round(cf_s, 4),
            "cb_score":      round(cb_s, 4),
            "reason":        cb_reason_map.get(asin, "Recommended for you"),
            "sources":       sources,
        })

    scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
    top_scored = scored[:top_k]

    if not top_scored:
        return {"user_id": user_id, "method": "hybrid", "products": []}

    # 8. Fetch full product details
    top_asins   = [s["asin"] for s in top_scored]
    score_index = {s["asin"]: s for s in top_scored}

    placeholders = ", ".join([f":a{i}" for i in range(len(top_asins))])
    params = {f"a{i}": a for i, a in enumerate(top_asins)}
    sql = text(f"SELECT * FROM amazon_products WHERE asin IN ({placeholders})")

    with state["engine"].connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    products = df.fillna("N/A").to_dict(orient="records")
    for p in products:
        meta = score_index.get(p["asin"], {})
        p["hybrid_score"] = meta.get("hybrid_score", 0.0)
        p["cf_score"]     = meta.get("cf_score", 0.0)
        p["cb_score"]     = meta.get("cb_score", 0.0)
        p["reason"]       = meta.get("reason", "")
        p["sources"]      = meta.get("sources", [])

    products.sort(key=lambda p: p["hybrid_score"], reverse=True)

    return {
        "user_id":   user_id,
        "method":    "hybrid",
        "cf_weight": cf_weight,
        "cb_weight": round(1.0 - cf_weight, 2),
        "total":     len(products),
        "products":  products,
    }


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8005, reload=True)
