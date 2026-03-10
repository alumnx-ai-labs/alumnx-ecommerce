"""

One-time (or on-demand) script to populate the Elasticsearch index
from your MySQL database.

"""

import argparse
import logging
import sys

from collaborative import build_engine        # reuse your existing DB engine builder
from elastic_search import get_es_client, create_index, index_products_from_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Build Elasticsearch product index")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete existing index and rebuild from scratch",
    )
    args = parser.parse_args()

    try:
        logger.info("🔌 Connecting to database ...")
        db_engine = build_engine()

        logger.info("🔌 Connecting to Elasticsearch ...")
        es = get_es_client()

        create_index(es, recreate=args.recreate)
        total = index_products_from_db(es, db_engine)

        logger.info(f"🎉 Done! {total:,} products are now searchable in Elasticsearch.")

    except ConnectionError as e:
        logger.error(f"Connection failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        try:
            db_engine.dispose()
        except Exception:
            pass


if __name__ == "__main__":
    main()