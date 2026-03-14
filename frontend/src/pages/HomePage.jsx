import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ProductService, UserService } from "../services/api";
import ProductCard from "../components/ProductCard";
import { ChevronLeft, ChevronRight, Search, Loader2 } from "lucide-react";

// Hardcoded to user 1 for demo (matches App.jsx navbar link)
const CURRENT_USER_ID = 1;

// Module-level cache — survives component unmount/remount (navigation away and back)
// so recommendations are shown instantly on return without a new API call.
const RECS_CACHE_TTL = 5 * 60 * 1000; // 5 minutes
let _recsCache = { products: [], ts: 0 };

export default function HomePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("search");
  const currentPage = parseInt(searchParams.get("page") || "1");

  // ── Products state ─────────────────────────────────────────────────
  const [products, setProducts] = useState([]);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ── Recommendations state — seeded from module cache if already fetched ──
  const [recommendations, setRecommendations] = useState(_recsCache.products);
  const [recsMethod, setRecsMethod] = useState(_recsCache.method || "");
  const [recsLoading, setRecsLoading] = useState(false);

  // ── Fetch products / search results ───────────────────────────────
  useEffect(() => {
    const fetchProducts = async () => {
      setLoading(true);
      setProducts([]);
      setError(null);
      try {
        let data;
        if (search) {
          data = await ProductService.searchProducts(search, 10);
        } else {
          data = await ProductService.getProducts(currentPage, 20);
        }
        setProducts(data.products || []);
        setTotalPages(data.total_pages || 1);
      } catch (err) {
        console.error("Error fetching products:", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchProducts();
    window.scrollTo(0, 0);
  }, [search, currentPage]);

  // ── Fetch hybrid recommendations (only on home page, not search) ──
  useEffect(() => {
    if (search) return;

    // Cache still fresh — use it instantly, no API call needed
    if (
      _recsCache.products.length > 0 &&
      Date.now() - _recsCache.ts < RECS_CACHE_TTL
    ) {
      setRecommendations(_recsCache.products);
      return;
    }

    const fetchRecs = async () => {
      setRecsLoading(true);
      try {
        const data = await UserService.getCollaborativeRecommendations(
          CURRENT_USER_ID,
          10,
        );
        const products = data.products || [];
        const method = data.method || "";
        // Store in module-level cache so next visit is instant
        _recsCache = { products, method, ts: Date.now() };
        setRecommendations(products);
        setRecsMethod(method);
      } catch (err) {
        console.error("Recommendations unavailable:", err.message);
        setRecommendations([]);
      } finally {
        setRecsLoading(false);
      }
    };

    fetchRecs();
  }, [search]);

  const handlePageChange = (newPage) => {
    if (newPage < 1 || newPage > totalPages) return;
    const params = new URLSearchParams(searchParams);
    params.set("page", newPage);
    setSearchParams(params);
  };

  if (loading && products.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center h-full"
        style={{ minHeight: "400px" }}
      >
        <Loader2 className="animate-spin text-amazon-orange mb-4" size={48} />
        <p className="text-gray-500 font-medium">Loading products...</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* ══════════════════════════════════════════════════════════
                RECOMMENDATIONS SECTION  —  shown only on home (no search)
            ══════════════════════════════════════════════════════════ */}
      {!search && (
        <section style={{ marginBottom: "32px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "10px",
              marginBottom: "12px",
              paddingLeft: "4px",
            }}
          >
            <h2
              style={{
                fontSize: "20px",
                fontWeight: "700",
                color: "#0F1111",
                margin: 0,
              }}
            >
              Recommended for you
            </h2>
            <span style={{ fontSize: "13px", color: "#007185" }}>
              {recsMethod === "popular"
                ? "Trending picks"
                : "Personalised picks · Collaborative Filtering"}
            </span>
          </div>

          {recsLoading ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "20px 0",
                color: "#565959",
              }}
            >
              <Loader2 className="animate-spin" size={20} />
              <span style={{ fontSize: "14px" }}>
                Computing your recommendations...
              </span>
            </div>
          ) : recommendations.length === 0 ? (
            <p
              style={{ fontSize: "14px", color: "#565959", padding: "12px 0" }}
            >
              Rate some products to get personalised recommendations.
            </p>
          ) : (
            /* Horizontal scrollable row — Amazon style */
            <div
              style={{
                display: "flex",
                gap: "12px",
                overflowX: "auto",
                paddingBottom: "8px",
                scrollbarWidth: "thin",
              }}
            >
              {recommendations.map((p) => (
                <div key={p.asin} style={{ flex: "0 0 180px" }}>
                  <ProductCard product={p} />
                </div>
              ))}
            </div>
          )}

          <hr style={{ borderColor: "#e7e7e7", margin: "24px 0 0" }} />
        </section>
      )}

      {/* ══════════════════════════════════════════════════════════
                PRODUCTS / SEARCH RESULTS SECTION
            ══════════════════════════════════════════════════════════ */}
      <section>
        <div className="flex justify-between items-end mb-4 px-2">
          <h2 className="text-[18px] font-bold text-[#0F1111]">
            {search && search.trim() !== ""
              ? `Results for "${search}"`
              : "All Products"}
          </h2>
          {!search && (
            <div className="text-[12px] text-[#565959]">
              Page {currentPage} of {totalPages?.toLocaleString() || totalPages}
            </div>
          )}
        </div>

        {error && (
          <div className="bg-white border border-red-300 text-red-600 p-4 rounded-md mb-8 text-center flex flex-col items-center gap-2">
            <p className="font-medium">Error: {error}</p>
            <button
              onClick={() => window.location.reload()}
              className="text-amazon-blue hover-underline font-medium"
            >
              Try Again
            </button>
          </div>
        )}

        {products.length === 0 && !loading ? (
          <div className="empty-state-container animate-fade-in">
            <div className="text-gray-400 mb-6">
              <Search size={64} className="mx-auto opacity-10" />
            </div>
            <h3 className="text-2xl font-bold text-gray-800 mb-2">
              No results for "{search}"
            </h3>
            <p className="text-gray-500 text-lg">
              Try checking your spelling or use more general terms
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
              {products.map((p) => (
                <ProductCard key={p.asin} product={p} />
              ))}
            </div>

            {/* Pagination — only for browse, not search */}
            {!search && (
              <div className="pagination-footer flex justify-center items-center gap-6">
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="pagination-btn-custom flex items-center gap-2"
                >
                  <ChevronLeft size={18} /> Previous
                </button>

                <div className="flex gap-2">
                  {[...Array(Math.min(5, totalPages))].map((_, i) => {
                    let pageNum;
                    if (totalPages <= 5) pageNum = i + 1;
                    else if (currentPage <= 3) pageNum = i + 1;
                    else if (currentPage >= totalPages - 2)
                      pageNum = totalPages - 4 + i;
                    else pageNum = currentPage - 2 + i;

                    if (pageNum <= 0 || pageNum > totalPages) return null;
                    return (
                      <button
                        key={pageNum}
                        onClick={() => handlePageChange(pageNum)}
                        className={`page-num-custom ${currentPage === pageNum ? "active" : ""}`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                </div>

                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="pagination-btn-custom flex items-center gap-2"
                >
                  Next <ChevronRight size={18} />
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
