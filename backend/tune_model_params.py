"""
tune_model_params.py
====================
Find optimal temperature and max_tokens for your model.

Usage:
    python tune_model_params.py --max-tokens 50 100 150 200
    python tune_model_params.py --temperatures 0.3 0.5 0.7 0.9
    python tune_model_params.py  # Tests defaults: temps [0.3-1.0] and tokens [50-200]
"""

import os
import asyncio
import argparse
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CUSTOM_API_BASE = os.getenv("CUSTOM_API_BASE", "http://3.109.63.164/gptoss/v1")
CUSTOM_API_KEY  = os.getenv("CUSTOM_API_KEY",  "dummy")
CUSTOM_MODEL    = os.getenv("CUSTOM_MODEL",    "gpt-oss:20b")

TIMEOUT = 180
PRODUCT_TITLE = "Collins Bird Guide: The Most Complete Guide to the Birds of Britain an"
PRICE = 29.44
RATING = 4.8

# ── Test ──────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    temperature: float
    max_tokens: int
    success: bool
    response_length: int
    error: Optional[str] = None
    time_seconds: float = 0.0
    
    def __repr__(self):
        if self.success:
            return (
                f"PASS | temp={self.temperature:.1f} | tokens={self.max_tokens:3d} | "
                f"length={self.response_length:3d} | time={self.time_seconds:.1f}s"
            )
        else:
            return (
                f"FAIL | temp={self.temperature:.1f} | tokens={self.max_tokens:3d} | "
                f"{self.error}"
            )


def build_prompt(title: str, price: float, rating: float) -> str:
    return (
        f"Write a 2-sentence product description for an e-commerce listing.\n"
        f"Product: {title}. It is rated {rating:.1f}/5 stars, priced at ${price:.2f}.\n"
        f"Rules: engaging tone, focus on benefits, no made-up specs, plain text only.\n"
        f"Output ONLY the description, nothing else."
    )


async def test_params(
    client: httpx.AsyncClient,
    temperature: float,
    max_tokens: int,
) -> TestResult:
    """Test a single temperature/max_tokens combination."""
    import time
    start = time.time()
    
    try:
        resp = await client.post(
            f"{CUSTOM_API_BASE}/chat/completions",
            json={
                "model": CUSTOM_MODEL,
                "messages": [{"role": "user", "content": build_prompt(PRODUCT_TITLE, PRICE, RATING)}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=TIMEOUT,
        )
        
        elapsed = time.time() - start
        
        if resp.status_code != 200:
            return TestResult(
                temperature=temperature,
                max_tokens=max_tokens,
                success=False,
                response_length=0,
                error=f"HTTP {resp.status_code}",
                time_seconds=elapsed,
            )
        
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        if not content:
            return TestResult(
                temperature=temperature,
                max_tokens=max_tokens,
                success=False,
                response_length=0,
                error="Empty response",
                time_seconds=elapsed,
            )
        
        return TestResult(
            temperature=temperature,
            max_tokens=max_tokens,
            success=True,
            response_length=len(content),
            time_seconds=elapsed,
        )
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        return TestResult(
            temperature=temperature,
            max_tokens=max_tokens,
            success=False,
            response_length=0,
            error="Timeout",
            time_seconds=elapsed,
        )
    except Exception as e:
        elapsed = time.time() - start
        return TestResult(
            temperature=temperature,
            max_tokens=max_tokens,
            success=False,
            response_length=0,
            error=str(e)[:50],
            time_seconds=elapsed,
        )


async def run_tests(
    temperatures: list[float],
    max_tokens_list: list[int],
):
    """Run all parameter combinations."""
    headers = {"Authorization": f"Bearer {CUSTOM_API_KEY}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(headers=headers, timeout=TIMEOUT) as client:
        # Connection test
        logger.info("🔌 Testing connection...")
        try:
            resp = await client.post(f"{CUSTOM_API_BASE}/chat/completions", json={
                "model": CUSTOM_MODEL,
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 5,
            })
            resp.raise_for_status()
            logger.info("✅ Model connected.\n")
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return
        
        results = []
        total = len(temperatures) * len(max_tokens_list)
        
        logger.info(f"🧪 Testing {total} parameter combinations...\n")
        
        for i, temp in enumerate(temperatures):
            for j, tokens in enumerate(max_tokens_list):
                idx = i * len(max_tokens_list) + j + 1
                logger.info(f"[{idx}/{total}] Testing temp={temp:.1f}, max_tokens={tokens}...")
                result = await test_params(client, temp, tokens)
                results.append(result)
                logger.info(f"       {result}\n")
                await asyncio.sleep(0.5)  # Be nice to the server
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info("RESULTS SUMMARY")
        logger.info("="*80 + "\n")
        
        successful = [r for r in results if r.success]
        if successful:
            logger.info("✅ SUCCESSFUL COMBINATIONS:\n")
            for r in sorted(successful, key=lambda x: -x.response_length):
                logger.info(f"  {r}")
            
            best = sorted(successful, key=lambda x: (x.time_seconds, x.response_length))[0]
            logger.info(f"\n🏆 BEST (fastest, good output):")
            logger.info(f"   Temperature: {best.temperature}")
            logger.info(f"   Max Tokens: {best.max_tokens}")
            logger.info(f"   Response Length: {best.response_length}")
            logger.info(f"   Time: {best.time_seconds:.1f}s\n")
            
            logger.info(f"📝 UPDATE generate_descriptions.py:")
            logger.info(f'   temp = {best.temperature}')
            logger.info(f'   max_tokens = {best.max_tokens}\n')
        
        failed = [r for r in results if not r.success]
        if failed:
            logger.info(f"❌ FAILED ({len(failed)} combinations):\n")
            for r in failed:
                logger.info(f"  {r}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find optimal temperature and max_tokens for your model"
    )
    parser.add_argument(
        "--temperatures",
        type=float,
        nargs="+",
        default=[0.3, 0.5, 0.7, 0.8, 0.9, 1.0],
        help="Temperatures to test (default: 0.3 0.5 0.7 0.8 0.9 1.0)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        nargs="+",
        default=[50, 100, 150, 200],
        help="Max token values to test (default: 50 100 150 200)",
    )
    args = parser.parse_args()
    
    asyncio.run(run_tests(args.temperatures, args.max_tokens))