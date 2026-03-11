import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def view_database():
    # DB Config
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT", 3306)
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        print("❌ Error: Missing database credentials in .env file.")
        return

    # Connection URL
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(url)

    try:
        with engine.connect() as conn:
            print(f"✅ Connected to RDS: {DB_NAME}\n")

            # 1. Show Tables
            print("--- Tables in Database ---")
            tables = conn.execute(text("SHOW TABLES")).fetchall()
            for table in tables:
                print(f" - {table[0]}")
            print("\n")

            # 2. Preview Products (Top 5)
            print("--- Preview: amazon_products (Top 5) ---")
            df_products = pd.read_sql(text("SELECT asin, title, price, stars FROM amazon_products LIMIT 5"), conn)
            print(df_products.to_markdown(index=False))
            print("\n")

            # 3. Preview Categories (Top 5)
            print("--- Preview: amazon_categories (Top 5) ---")
            df_categories = pd.read_sql(text("SELECT * FROM amazon_categories LIMIT 5"), conn)
            print(df_categories.to_markdown(index=False))
            print("\n")

            # 4. Product Count
            count = conn.execute(text("SELECT COUNT(*) FROM amazon_products")).scalar()
            print(f"📊 Total products in database: {count}")

    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    view_database()
