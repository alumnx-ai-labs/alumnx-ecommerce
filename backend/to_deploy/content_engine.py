import pandas as pd
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import text

# ── Logging ─────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── Step 1: Data Loader ───────────────────────────────────────────────────────

def load_product_catalog(engine):
    """Loads all products from the amazon_products table for content analysis."""
    logger.info("Loading product catalog ...")
    query = "SELECT asin, title, category_id, stars, reviews, img_url, price FROM amazon_products"
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    logger.info(f" → {len(df):,} products loaded")
    return df


# ── Step 2: TF-IDF Pipeline ───────────────────────────────────────────────────

def build_tfidf_matrix(product_df):
    """Vectorizes product titles to enable content-based filtering."""
    logger.info("Building TF-IDF matrix ...")
    
    # Fill empty titles
    product_df["title"] = product_df["title"].fillna("")
    
    vectorizer = TfidfVectorizer(stop_words="english", max_features=10_000)
    tfidf_matrix = vectorizer.fit_transform(product_df["title"])
    
    # Map ASIN to dataframe index for quick lookups
    product_index = pd.Series(product_df.index, index=product_df["asin"]).drop_duplicates()
    
    logger.info(f" → TF-IDF Matrix shape: {tfidf_matrix.shape}")
    return tfidf_matrix, product_index, vectorizer


# ── Step 3: Recommendation Logic ──────────────────────────────────────────────

def get_content_recommendations(user_id, matrix, tfidf_matrix, product_index, top_n=10):
    """Recommends products similar to what the user has rated highly (stars >= 4)."""
    if user_id not in matrix.index:
        logger.warning(f"User {user_id} not found in matrix. Cannot provide content recommendations.")
        return pd.DataFrame()

    # Get positive interactions
    user_ratings = matrix.loc[user_id]
    positive_items = user_ratings[user_ratings >= 4].index.tolist()

    if not positive_items:
        logger.info(f"User {user_id} has no high ratings. Returning empty recommendations.")
        return pd.DataFrame()

    # Only include items that are in the TF-IDF index
    valid_items = [item for item in positive_items if item in product_index]

    if not valid_items:
        logger.info(f"User {user_id}'s rated items not found in catalog. Returning empty.")
        return pd.DataFrame()

    # Get item vectors for positive items
    indices = [product_index[item] for item in valid_items]
    user_profile_vec = tfidf_matrix[indices].mean(axis=0)

    # Compute similarity between user profile and all items
    sim_scores = cosine_similarity(user_profile_vec, tfidf_matrix).flatten()

    # Filter out items the user already rated
    rated_items = user_ratings[user_ratings > 0].index.tolist()
    rated_indices = [product_index[item] for item in rated_items if item in product_index]
    sim_scores[rated_indices] = -1

    # Get top N
    top_indices = sim_scores.argsort()[-top_n:][::-1]
    
    rec_df = pd.DataFrame({
        "product_id"   : product_index.index[top_indices],
        "content_score": sim_scores[top_indices]
    })
    
    return rec_df


def get_item_similarity(asin, tfidf_matrix, product_index, top_n=10):
    """Recommends products similar to a specific ASIN (Item-Item)."""
    if asin not in product_index:
        logger.warning(f"Product {asin} not found in catalog.")
        return pd.DataFrame()
    
    idx = product_index[asin]
    item_vec = tfidf_matrix[idx]
    
    # Compute similarity against all items
    sim_scores = cosine_similarity(item_vec, tfidf_matrix).flatten()
    
    # Exclude the item itself
    sim_scores[idx] = -1
    
    # Get top N
    top_indices = sim_scores.argsort()[-top_n:][::-1]
    
    rec_df = pd.DataFrame({
        "product_id"   : product_index.index[top_indices],
        "content_score": sim_scores[top_indices]
    })
    
    return rec_df


# ── Step 4: Load Content Model ────────────────────────────────────────────────

def load_content_model(engine):
    """Initializes the content-based engine."""
    product_df                               = load_product_catalog(engine)
    tfidf_matrix, product_index, vectorizer  = build_tfidf_matrix(product_df)
    logger.info("✓ Content model ready")
    return product_df, tfidf_matrix, product_index, vectorizer


# ── Main (standalone) ─────────────────────────────────────────────────────────

def main():
    from collaborative import build_engine, load_model, enrich_with_product_details

    engine = build_engine()
    matrix, _ = load_model(engine)

    product_df, tfidf_matrix, product_index, _ = load_content_model(engine)

    sample_user_id = matrix.index[0]
    logger.info(f"\n── Content Recs for User {sample_user_id} ──")

    rec_df = get_content_recommendations(sample_user_id, matrix, tfidf_matrix, product_index)
    rec_df = enrich_with_product_details(rec_df, engine)

    print("\n" + "="*70)
    print(f" Top 10 Content-Based Recs for User: {sample_user_id}")
    print("="*70)
    print(rec_df[["product_id", "product_name", "content_score", "price"]].to_string())
    print("="*70)

    engine.dispose()


if __name__ == "__main__":
    main()
