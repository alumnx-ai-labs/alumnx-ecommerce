"""
generate_descriptions.py (Production - Three-Stage Strategy)
============================================================
High-throughput description generation with intelligent fallback cascade.

Key insight:
- Some titles fail BOTH primary and fallback prompts
- Root cause: Complex titles confuse the model at generation level
- Solution: Add EMERGENCY prompt (ultra-minimal) for edge cases

Strategy:
1. PRIMARY: Rich prompt with full context (works 70-80%)
2. FALLBACK: Simple prompt, title only (works for 15-20%)
3. EMERGENCY: Ultra-minimal, simplified title only (works for remaining 5%)

Expected: >98% success rate with three-stage fallback

Run:
    python generate_descriptions.py --dry-run
    python generate_descriptions.py --concurrency 50
"""

import os
import asyncio
import logging
import argparse
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("generate_descriptions.log")
    ]
)
logger = logging.getLogger(__name__)

#  Config 

CUSTOM_API_BASE = os.getenv("CUSTOM_API_BASE", "http://3.109.63.164/gptoss/v1")
CUSTOM_API_KEY  = os.getenv("CUSTOM_API_KEY",  "dummy")
CUSTOM_MODEL    = os.getenv("CUSTOM_MODEL",    "gpt-oss:20b")

CONCURRENCY  = 50  # Reduced from 100 to prevent semaphore deadlock
CHUNK_SIZE   = 2000
COMMIT_EVERY = 200
TIMEOUT      = 30  # Reduced from 90 to catch hangs faster

# Tuned params
TEMPERATURE = 0.8
MAX_TOKENS  = 150

#  DB 

def get_engine():
    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT", "3306")
    name     = os.getenv("DB_NAME")
    user     = os.getenv("DB_USER")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    url      = f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def ensure_description_column(engine):
    with engine.begin() as conn:
        cols = [r[0] for r in conn.execute(text("DESCRIBE amazon_products")).fetchall()]
        if "description" not in cols:
            conn.execute(text("ALTER TABLE amazon_products ADD COLUMN description TEXT NULL"))
            logger.info("[OK] `description` column created.")
        else:
            logger.info("[OK] `description` column already exists.")


def fetch_chunk(engine, last_asin: str, chunk_size: int) -> list:
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT
                asin         AS product_id,
                title,
                price,
                stars        AS avg_rating,
                isBestSeller AS is_bestseller,
                listPrice    AS list_price
            FROM amazon_products
            WHERE asin > :last_asin
              AND title IS NOT NULL
              AND price > 0
              AND description IS NULL
            ORDER BY asin
            LIMIT :chunk_size
        """), {"last_asin": last_asin, "chunk_size": chunk_size}).fetchall()


def bulk_save(engine, updates: list):
    if not updates:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE amazon_products SET description = :desc WHERE asin = :asin"),
                updates,
            )
        logger.debug(f"   Saved {len(updates)} to DB")
    except Exception as e:
        logger.error(f"   BULK_SAVE ERROR: {type(e).__name__}: {e}")


#  Prompt Strategy (3-Stage Fallback) 

def build_primary_prompt(row) -> str:
    """Rich, detailed prompt with full context."""
    extras = []
    if row.avg_rating:    extras.append(f"rated {row.avg_rating:.1f}/5 stars")
    if row.price:         extras.append(f"priced at ${row.price:.2f}")
    if row.is_bestseller: extras.append("a bestseller")
    if row.list_price and row.price and row.list_price > row.price * 1.05:
        extras.append(f"originally ${row.list_price:.2f}")
    extra_str = f" It is {', '.join(extras)}." if extras else ""

    return (
        f"Write a 2-sentence product description for an e-commerce listing.\n"
        f"Product: {row.title}{extra_str}\n"
        f"Rules: engaging tone, focus on benefits, no made-up specs, plain text only.\n"
        f"Output ONLY the description, nothing else."
    )


def build_fallback_prompt(row) -> str:
    """Simple prompt with less context."""
    return (
        f"Write a concise product description in 1-2 sentences.\n"
        f"Product: {row.title}\n"
        f"Be brief and direct."
    )


def build_emergency_prompt(row) -> str:
    """Ultra-minimal prompt for edge cases (removes confusing elements)."""
    # Strip complex subtitles that confuse the model
    # "The Silmarillion: Tales from Middle Earth" -> "The Silmarillion"
    title = row.title.split(':')[0].strip()
    title = title.split(' - ')[0].strip()
    
    return f"In 1 sentence, describe: {title}"


#  Async Generation (3-Stage Fallback) 

async def generate_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    row,
    attempt: int = 1,
) -> dict | None:
    """Generate with 3-stage fallback: PRIMARY -> FALLBACK -> EMERGENCY."""
    async with semaphore:
        try:
            # Choose prompt based on attempt
            if attempt == 1:
                prompt = build_primary_prompt(row)
                prompt_type = "primary"
            elif attempt == 2:
                prompt = build_fallback_prompt(row)
                prompt_type = "fallback"
            else:
                prompt = build_emergency_prompt(row)
                prompt_type = "emergency"
            
            resp = await client.post(
                f"{CUSTOM_API_BASE}/chat/completions",
                json={
                    "model"      : CUSTOM_MODEL,
                    "messages"   : [{"role": "user", "content": prompt}],
                    "max_tokens" : MAX_TOKENS,
                    "temperature": TEMPERATURE,
                },
                timeout=TIMEOUT,
            )
            
            # Check HTTP status
            if resp.status_code != 200:
                if attempt < 3:
                    await asyncio.sleep(0.1)
                    return await generate_one(client, semaphore, row, attempt + 1)
                logger.debug(f"[FAIL] {row.product_id}: HTTP {resp.status_code} on all attempts")
                return None
            
            # Parse JSON
            try:
                data = resp.json()
            except Exception as e:
                if attempt < 3:
                    await asyncio.sleep(0.1)
                    return await generate_one(client, semaphore, row, attempt + 1)
                logger.debug(f"[FAIL] {row.product_id}: JSON error on all attempts")
                return None
            
            # Validate structure
            if "choices" not in data or not data["choices"]:
                if attempt < 3:
                    await asyncio.sleep(0.1)
                    return await generate_one(client, semaphore, row, attempt + 1)
                return None
            
            choice = data["choices"][0]
            if "message" not in choice or "content" not in choice["message"]:
                if attempt < 3:
                    await asyncio.sleep(0.1)
                    return await generate_one(client, semaphore, row, attempt + 1)
                return None
            
            desc = choice["message"]["content"].strip()
            
            # If empty, try next stage
            if not desc:
                if attempt < 3:
                    logger.debug(f"  Empty on {prompt_type}, trying next stage...")
                    await asyncio.sleep(0.1)
                    return await generate_one(client, semaphore, row, attempt + 1)
                logger.debug(f"[FAIL] {row.product_id}: Empty on all 3 stages")
                return None
            
            return {"asin": row.product_id, "desc": desc, "prompt_type": prompt_type}

        except asyncio.TimeoutError:
            if attempt < 3:
                logger.debug(f"  Timeout on attempt {attempt}, trying next...")
                await asyncio.sleep(0.1)
                return await generate_one(client, semaphore, row, attempt + 1)
            logger.debug(f"[FAIL] {row.product_id}: Timeout on all attempts")
            return None
            
        except Exception as e:
            if attempt < 3:
                await asyncio.sleep(0.1)
                return await generate_one(client, semaphore, row, attempt + 1)
            logger.debug(f"[FAIL] {row.product_id}: {type(e).__name__}")
            return None


#  Main 

async def run_async(concurrency: int, dry_run: bool):
    engine = get_engine()
    last_asin = ""
    saved = 0
    failed = 0
    stage_1 = 0  # Primary prompt successes
    stage_2 = 0  # Fallback prompt successes
    stage_3 = 0  # Emergency prompt successes

    if not dry_run:
        ensure_description_column(engine)

    headers   = {"Authorization": f"Bearer {CUSTOM_API_KEY}", "Content-Type": "application/json"}
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT) as client:

        # Connection test
        logger.info(" Testing connection ...")
        try:
            resp = await client.post(f"{CUSTOM_API_BASE}/chat/completions", json={
                "model": CUSTOM_MODEL,
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 5,
            })
            resp.raise_for_status()
            logger.info("[OK] Model connected.")
        except Exception as e:
            logger.error(f"[FAIL] Connection failed: {e}")
            return

        if dry_run:
            rows = fetch_chunk(engine, "", 3)
            logger.info(f" DRY RUN - 3 products with PRIMARY -> FALLBACK -> EMERGENCY strategy:\n")
            tasks   = [generate_one(client, semaphore, row) for row in rows]
            results = await asyncio.gather(*tasks)
            
            for row, result in zip(rows, results):
                print(f"Title : {row.title[:70]}")
                if result:
                    stage_label = {
                        "primary": "(primary)",
                        "fallback": "(fallback)",
                        "emergency": "(emergency)"
                    }.get(result['prompt_type'], "")
                    print(f"Desc  : {result['desc'][:120]}... {stage_label}\n")
                else:
                    print(f"Desc  : FAILED\n")
            
            success_count = sum(1 for r in results if r)
            logger.info(f" Success rate in test: {success_count}/3 ({success_count*100//3}%)")
            if success_count == 3:
                logger.info("[OK] All tests passed! Ready for production.")
            return

        products_per_sec = concurrency / 5
        eta_hours        = 1_393_564 / products_per_sec / 3600
        logger.info(f" Starting | concurrency={concurrency} | ~{products_per_sec:.0f} products/sec | ETA ~{eta_hours:.1f}h")
        logger.info(f"[CONFIG]  Using 3-STAGE FALLBACK: Primary -> Fallback -> Emergency")

        chunk_count = 0
        while True:
            rows = fetch_chunk(engine, last_asin, CHUNK_SIZE)
            if not rows:
                break

            chunk_count += 1
            logger.info(f" Processing chunk {chunk_count} ({len(rows)} products)...")

            pending = []
            chunk_saved = 0
            chunk_failed = 0
            
            # Process in batches to avoid semaphore deadlock
            batch_size = 10  # Reduced from 30 to 10 products per batch
            
            for batch_start in range(0, len(rows), batch_size):
                batch_end = min(batch_start + batch_size, len(rows))
                batch = rows[batch_start:batch_end]
                
                logger.info(f"   Batch {batch_start//batch_size + 1}: processing {len(batch)} products...")
                
                try:
                    tasks = [generate_one(client, semaphore, row) for row in batch]
                    results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=300.0  # 5 min per batch (10 products * ~20-30s each)
                    )
                except asyncio.TimeoutError:
                    logger.error(f"   TIMEOUT on batch {batch_start//batch_size + 1}")
                    results = [None] * len(batch)
                except Exception as e:
                    logger.error(f"   ERROR on batch: {type(e).__name__}: {e}")
                    results = [None] * len(batch)
                
                for result in results:
                    if result:
                        pending.append({"asin": result["asin"], "desc": result["desc"]})
                        saved += 1
                        chunk_saved += 1
                        
                        if result.get("prompt_type") == "primary":
                            stage_1 += 1
                        elif result.get("prompt_type") == "fallback":
                            stage_2 += 1
                        elif result.get("prompt_type") == "emergency":
                            stage_3 += 1
                        
                        if len(pending) >= COMMIT_EVERY:
                            bulk_save(engine, pending)
                            pending = []
                    else:
                        failed += 1
                        chunk_failed += 1

            if pending:
                bulk_save(engine, pending)

            last_asin = rows[-1].product_id
            
            # Log chunk summary with detailed metrics
            success_pct = (chunk_saved * 100) // len(rows) if rows else 0
            total_success_pct = (saved * 100) // (saved + failed) if (saved + failed) > 0 else 0
            
            logger.info(
                f"[OK] CHUNK {chunk_count} COMPLETE"
            )
            logger.info(
                f"   Chunk: {chunk_saved} descriptions added | {chunk_failed} failed ({success_pct}% success)"
            )
            logger.info(
                f"   TOTAL: {saved:,} descriptions added | {failed} failed | {total_success_pct}% success rate"
            )
            logger.info(
                f"   Stages: PRIMARY={stage_1:,} | FALLBACK={stage_2:,} | EMERGENCY={stage_3:,}"
            )
            logger.info("")

    logger.info("")
    logger.info("=" * 80)
    logger.info(" JOB COMPLETED!")
    logger.info("=" * 80)
    logger.info(f"Total Descriptions Added: {saved:,}")
    logger.info(f"Total Failed: {failed}")
    logger.info(f"Success Rate: {(saved*100)//(saved+failed) if (saved+failed) > 0 else 0}%")
    logger.info("")
    logger.info("Breakdown by Stage:")
    logger.info(f"  [OK] PRIMARY Prompt:   {stage_1:,} descriptions")
    logger.info(f"  [WARN]  FALLBACK Prompt:  {stage_2:,} descriptions")
    logger.info(f"  [EMERGENCY] EMERGENCY Prompt: {stage_3:,} descriptions")
    logger.info("")
    logger.info("=" * 80)
    logger.info(" Next step: python semantic_search.py --index")
    logger.info("=" * 80)


def run(concurrency: int, dry_run: bool):
    asyncio.run(run_async(concurrency, dry_run))


#  CLI 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY,
                        help=f"Simultaneous API calls (default: {CONCURRENCY})")
    parser.add_argument("--dry-run",     action="store_true")
    args = parser.parse_args()
    run(concurrency=args.concurrency, dry_run=args.dry_run)