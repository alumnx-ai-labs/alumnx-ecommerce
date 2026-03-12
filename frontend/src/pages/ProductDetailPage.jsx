import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { ProductService } from "../services/api";
import ProductCard from "../components/ProductCard";

export default function ProductDetailPage() {
  const { asin } = useParams();
  const [product, setProduct] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchProduct = async () => {
      setLoading(true);
      setSimilar([]);
      try {
        const prod = await ProductService.getProduct(asin);
        setProduct(prod);

        // Semantic search by title to find similar products
        if (prod?.title) {
          try {
            const simData = await ProductService.searchProducts(prod.title, 7);
            // Exclude the current product from results
            setSimilar(
              (simData.products || [])
                .filter((p) => p.asin !== asin)
                .slice(0, 6),
            );
          } catch (e) {
            console.log("Similar products unavailable:", e.message);
          }
        }
      } catch (err) {
        console.error("Error fetching product:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchProduct();
  }, [asin]);

  if (loading)
    return <div style={{ padding: "40px" }}>Loading product details...</div>;
  if (!product)
    return <div style={{ padding: "40px" }}>Product not found.</div>;

  return (
    <div>
      <div
        className="card"
        style={{ display: "flex", gap: "40px", marginBottom: "40px" }}
      >
        {/* Left Side: Image */}
        <div
          style={{
            flex: "0 0 400px",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          {product.imgUrl && product.imgUrl !== "N/A" ? (
            <img
              src={product.imgUrl}
              alt={product.title}
              style={{
                maxWidth: "100%",
                maxHeight: "400px",
                objectFit: "contain",
              }}
            />
          ) : (
            <div style={{ padding: "100px", background: "#f8f8f8" }}>
              No Image Available
            </div>
          )}
        </div>

        {/* Right Side: Details */}
        <div style={{ flex: 1, paddingRight: "20px" }}>
          <h1
            style={{
              fontSize: "24px",
              fontWeight: "400",
              marginBottom: "10px",
            }}
          >
            {product.title}
          </h1>
          <div
            style={{
              color: "var(--amazon-link)",
              marginBottom: "15px",
              fontSize: "14px",
              cursor: "pointer",
            }}
          >
            Visit the Store
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              paddingBottom: "15px",
              borderBottom: "1px solid #ddd",
              marginBottom: "15px",
            }}
          >
            <span style={{ color: "var(--amazon-orange)" }}>
              {"★".repeat(Math.round(product.stars || 0)) +
                "☆".repeat(5 - Math.round(product.stars || 0))}
            </span>
            <span style={{ color: "var(--amazon-link)" }}>
              {product.reviews?.toLocaleString()} ratings
            </span>
            {product.isBestSeller && (
              <span
                style={{
                  background: "#e86900",
                  color: "white",
                  padding: "2px 6px",
                  fontSize: "12px",
                  borderRadius: "2px",
                }}
              >
                #1 Best Seller
              </span>
            )}
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "5px",
              marginBottom: "20px",
            }}
          >
            <span
              style={{
                fontSize: "14px",
                alignSelf: "flex-start",
                marginTop: "4px",
              }}
            >
              $
            </span>
            <span style={{ fontSize: "28px", fontWeight: "500" }}>
              {Math.floor(product.price || 0)}
            </span>
            <span
              style={{
                fontSize: "14px",
                alignSelf: "flex-start",
                marginTop: "4px",
              }}
            >
              {((product.price || 0) % 1).toFixed(2).substring(2)}
            </span>
            {product.listPrice > product.price && (
              <span
                style={{
                  color: "#565959",
                  textDecoration: "line-through",
                  marginLeft: "10px",
                }}
              >
                List: ${product.listPrice}
              </span>
            )}
          </div>

          <div
            style={{ marginBottom: "30px", fontSize: "14px", color: "#565959" }}
          >
            <p>
              <strong>Category ID:</strong> {product.category_id}
            </p>
            <p>
              <strong>Bought last month:</strong>{" "}
              {product.boughtInLastMonth?.toLocaleString()}+
            </p>
          </div>

          <button
            className="btn-amazon"
            style={{ width: "250px", padding: "12px" }}
          >
            Add to Cart
          </button>
        </div>
      </div>

      {similar.length > 0 && (
        <section>
          <h2 className="section-title">Similar products you might like</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "20px",
            }}
          >
            {similar.map((p) => (
              <ProductCard key={p.asin} product={p} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
