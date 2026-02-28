import { Link } from "react-router-dom";

export default function ProductCard({ product }) {
    return (
        <Link to={`/product/${product.asin}`} style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '100%', cursor: 'pointer' }}>
                <div style={{ height: '200px', width: '100%', marginBottom: '15px', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8f8f8', borderRadius: '4px', overflow: 'hidden' }}>
                    {product.imgUrl ? (
                        <img
                            src={product.imgUrl}
                            alt={product.title}
                            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                            onError={(e) => { e.target.src = 'https://via.placeholder.com/200x200?text=No+Image'; }}
                        />
                    ) : (
                        <div style={{ color: '#aaa' }}>No Image</div>
                    )}
                </div>

                <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '500', marginBottom: '8px', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', color: '#0f1111' }}>
                        {product.title}
                    </h3>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                        <div style={{ color: 'var(--amazon-orange)', fontSize: '14px' }}>
                            {"★".repeat(Math.round(product.stars || 0)) + "☆".repeat(5 - Math.round(product.stars || 0))}
                        </div>
                        <span style={{ color: '#007185', fontSize: '14px' }}>{product.reviews?.toLocaleString()}</span>
                    </div>

                    <div style={{ fontSize: '24px', fontWeight: '500', marginTop: 'auto', marginBottom: '10px' }}>
                        <span style={{ fontSize: '14px', verticalAlign: 'top' }}>$</span>
                        {Math.floor(product.price || 0)}
                        <span style={{ fontSize: '14px', verticalAlign: 'top' }}>
                            {((product.price || 0) % 1).toFixed(2).substring(2)}
                        </span>
                    </div>

                    <button className="btn-amazon" onClick={(e) => { e.preventDefault(); alert("Added to cart!"); }}>
                        Add to cart
                    </button>
                </div>
            </div>
        </Link>
    );
}
