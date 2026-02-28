import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import ProductCard from "../components/ProductCard";
import { ChevronLeft, ChevronRight } from "lucide-react";

// Mock API base URL - in production use env var
const API_BASE = "http://localhost:8000/api";

export default function HomePage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const search = searchParams.get("search");
    const currentPage = parseInt(searchParams.get("page") || "1");

    const [products, setProducts] = useState([]);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchProducts = async () => {
            setLoading(true);
            try {
                let url = `${API_BASE}/products?page=${currentPage}&size=20`;
                if (search) {
                    url += `&search=${encodeURIComponent(search)}`;
                }

                const res = await axios.get(url);
                setProducts(res.data.items || []);
                setTotalPages(res.data.pages || 1);
            } catch (err) {
                console.error("Error fetching products:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchProducts();
        // Scroll to top when page changes
        window.scrollTo(0, 0);
    }, [search, currentPage]);

    const handlePageChange = (newPage) => {
        const params = new URLSearchParams(searchParams);
        params.set("page", newPage);
        setSearchParams(params);
    };

    if (loading) {
        return <div style={{ padding: "100px", textAlign: "center" }}>
            <div className="spinner" style={{ margin: "0 auto 20px auto" }}></div>
            Loading Products...
        </div>;
    }

    return (
        <div>
            <section>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                    <h2 className="section-title" style={{ margin: 0 }}>
                        {search ? `Results for "${search}"` : "All Products"}
                    </h2>
                    <div style={{ fontSize: "14px", color: "#565959" }}>
                        Page {currentPage} of {totalPages}
                    </div>
                </div>

                {products.length === 0 ? (
                    <div style={{ textAlign: "center", padding: "40px" }}>
                        <p>No products found.</p>
                    </div>
                ) : (
                    <>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "20px" }}>
                            {products.map(p => <ProductCard key={p.asin} product={p} />)}
                        </div>

                        {/* Pagination Controls */}
                        <div style={{
                            display: "flex",
                            justifyContent: "center",
                            alignItems: "center",
                            gap: "10px",
                            marginTop: "40px",
                            padding: "20px 0"
                        }}>
                            <button
                                onClick={() => handlePageChange(currentPage - 1)}
                                disabled={currentPage === 1}
                                className="pagination-btn"
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    padding: "8px 15px",
                                    background: currentPage === 1 ? "#f7f7f7" : "white",
                                    border: "1px solid #ddd",
                                    borderRadius: "4px",
                                    cursor: currentPage === 1 ? "not-allowed" : "pointer",
                                    color: currentPage === 1 ? "#aaa" : "#111"
                                }}
                            >
                                <ChevronLeft size={18} /> Previous
                            </button>

                            <div style={{ display: "flex", gap: "5px" }}>
                                {[...Array(Math.min(5, totalPages))].map((_, i) => {
                                    // Simple logic to show pages around current
                                    let pageNum = currentPage;
                                    if (currentPage <= 3) pageNum = i + 1;
                                    else if (currentPage >= totalPages - 2) pageNum = totalPages - 4 + i;
                                    else pageNum = currentPage - 2 + i;

                                    if (pageNum <= 0 || pageNum > totalPages) return null;

                                    return (
                                        <button
                                            key={pageNum}
                                            onClick={() => handlePageChange(pageNum)}
                                            style={{
                                                width: "35px",
                                                height: "35px",
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "center",
                                                border: "1px solid #ddd",
                                                borderRadius: "4px",
                                                background: currentPage === pageNum ? "var(--amazon-orange)" : "white",
                                                borderColor: currentPage === pageNum ? "var(--amazon-orange)" : "#ddd",
                                                fontWeight: currentPage === pageNum ? "bold" : "normal",
                                                cursor: "pointer"
                                            }}
                                        >
                                            {pageNum}
                                        </button>
                                    );
                                })}
                            </div>

                            <button
                                onClick={() => handlePageChange(currentPage + 1)}
                                disabled={currentPage === totalPages}
                                className="pagination-btn"
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    padding: "8px 15px",
                                    background: currentPage === totalPages ? "#f7f7f7" : "white",
                                    border: "1px solid #ddd",
                                    borderRadius: "4px",
                                    cursor: currentPage === totalPages ? "not-allowed" : "pointer",
                                    color: currentPage === totalPages ? "#aaa" : "#111"
                                }}
                            >
                                Next <ChevronRight size={18} />
                            </button>
                        </div>
                    </>
                )}
            </section>
        </div>
    );
}
