import { Link } from "react-router-dom";
import { Star } from "lucide-react";

export default function ProductCard({ product }) {
  const wholePart = Math.floor(product.price || 0);
  const centsPart = Math.round(((product.price || 0) % 1) * 100)
    .toString()
    .padStart(2, "0");

  return (
    <div
      className="product-card"
      style={{
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#fff",
        border: "1px solid #D5D9D9",
        borderRadius: "4px",
        overflow: "hidden",
        height: "100%",
      }}
    >
      {/* ── Image area ─────────────────────────────────────────── */}
      <Link
        to={`/product/${product.asin}`}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "208px",
          backgroundColor: "#F8F8F8",
          padding: "16px",
          flexShrink: 0,
        }}
      >
        {product.imgUrl ? (
          <img
            src={product.imgUrl}
            alt={product.title}
            className="product-img"
            style={{
              maxHeight: "100%",
              maxWidth: "100%",
              objectFit: "contain",
              mixBlendMode: "multiply",
            }}
            onError={(e) => {
              e.target.src =
                "https://via.placeholder.com/200x200?text=No+Image";
            }}
          />
        ) : (
          <span style={{ color: "#ccc", fontSize: "11px" }}>No Image</span>
        )}
      </Link>

      {/* ── Content area ───────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          padding: "12px",
          gap: "6px",
        }}
      >
        {/* Title */}
        <div style={{ minHeight: "40px", overflow: "hidden" }}>
          <Link
            to={`/product/${product.asin}`}
            className="line-clamp-2"
            style={{
              fontSize: "13px",
              lineHeight: "1.4",
              color: "#0F1111",
              textDecoration: "none",
              fontWeight: "normal",
            }}
            onMouseEnter={(e) => (e.target.style.color = "#C45500")}
            onMouseLeave={(e) => (e.target.style.color = "#0F1111")}
          >
            {product.title}
          </Link>
        </div>

        {/* Stars + review count */}
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <div style={{ display: "flex", color: "#FFA41C" }}>
            {[...Array(5)].map((_, i) => (
              <Star
                key={i}
                size={13}
                fill={
                  i < Math.round(product.stars || 0) ? "currentColor" : "none"
                }
                strokeWidth={1}
                style={{
                  color:
                    i < Math.round(product.stars || 0) ? "#FFA41C" : "#DDD",
                }}
              />
            ))}
          </div>
          <span style={{ fontSize: "11px", color: "#007185" }}>
            {product.reviews || 0}
          </span>
        </div>

        {/* Price — Amazon superscript style: $139⁹⁹ */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            color: "#0F1111",
            marginTop: "2px",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: "500",
              lineHeight: 1,
              paddingTop: "3px",
            }}
          >
            $
          </span>
          <span
            style={{
              fontSize: "22px",
              fontWeight: "500",
              lineHeight: 1,
              letterSpacing: "-0.5px",
            }}
          >
            {wholePart}
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "500",
              lineHeight: 1,
              paddingTop: "3px",
            }}
          >
            {centsPart}
          </span>
        </div>

        {/* Add to cart button */}
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            alert("Added to cart!");
          }}
          className="product-cart-btn"
          style={{
            marginTop: "auto",
            width: "100%",
            backgroundColor: "#FFD814",
            border: "1px solid #FCD200",
            borderRadius: "9999px",
            padding: "7px 8px",
            fontSize: "13px",
            fontWeight: "500",
            color: "#0F1111",
            cursor: "pointer",
          }}
        >
          Add to cart
        </button>
      </div>
    </div>
  );
}
