"""
FastAPI Amazon Product API (Recommendation Engine Removed)

Endpoints:
  GET  /health                              → API + DB status
  GET  /users/{user_id}/profile             → User info + ratings
  GET  /stats                               → Overall system stats
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from dotenv import load_dotenv
import pandas as pd
import logging
from datetime import datetime
import os

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Amazon Product API",
    description="""
    Core Product and User API. Recommendation Engine has been decommissioned.
    """,
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global State ───────────────────────────────────────────────────────────────
state = {
    "engine":            None,
    "ready":             False,
}

# ── Configuration ──────────────────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# ── Helper: Run SQL and return DataFrame ───────────────────────────────────────

def query_db(sql: str, params: dict = None) -> pd.DataFrame:
    if params is None:
        params = {}
    with state["engine"].connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)

def build_engine():
    from sqlalchemy import create_engine
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url, pool_pre_ping=True)

# ── Startup: Connect DB ──────────────────────────────────────────

@app.on_event("startup")
def startup():
    logger.info(f"Starting up API from {os.path.abspath(__file__)} ...")
    engine = build_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("✓ Connected to RDS")

    state["engine"]            = engine
    state["ready"]             = True
    logger.info("✓ API ready")


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

    # img_url is now the primary column name in DB
    sql = f"""
        SELECT 
            asin, title, stars, reviews, price, category_id,
            img_url, video_url
        FROM amazon_products 
        {where_clause} 
        LIMIT :limit OFFSET :offset
    """
    try:
        with state["engine"].connect() as conn:
            # Get true total count for proper pagination
            count_sql = f"SELECT COUNT(*) FROM amazon_products {where_clause}"
            total_count = conn.execute(text(count_sql), params).scalar()
            logger.info(f"Querying products: {sql} with params {params}")
            df = pd.read_sql(text(sql), conn, params=params)
            logger.info(f"Query returned {len(df)} rows")
        return {
            "page": page,
            "limit": limit,
            "total_count": int(total_count),
            "total_pages": (int(total_count) + limit - 1) // limit,
            "products": df.fillna("N/A").to_dict(orient="records")
        }
    except Exception as e:
        logger.error(f"Products query failed: {e}")
        return {"page": page, "limit": limit, "total_count": 0, "total_pages": 0, "products": []}

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


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8005, reload=True)
