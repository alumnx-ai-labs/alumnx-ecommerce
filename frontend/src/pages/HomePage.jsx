import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ProductService } from "../services/api";
import ProductCard from "../components/ProductCard";
import { ChevronLeft, ChevronRight, Search, Loader2 } from "lucide-react";

export default function HomePage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const search = searchParams.get("search");
    const currentPage = parseInt(searchParams.get("page") || "1");

    const [products, setProducts] = useState([]);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchProducts = async () => {
            setLoading(true);
            setProducts([]); // Clear previous results immediately
            setError(null);
            try {
                let data;
                if (search) {
                    console.log(`Searching for: ${search}`);
                    data = await ProductService.searchProducts(search, 10);
                } else {
                    console.log(`Fetching products for page: ${currentPage}`);
                    data = await ProductService.getProducts(currentPage, 20);
                }

                console.log("Received data:", data);
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

    const handlePageChange = (newPage) => {
        if (newPage < 1 || newPage > totalPages) return;
        const params = new URLSearchParams(searchParams);
        params.set("page", newPage);
        setSearchParams(params);
    };

    const handleSearchSubmit = (e) => {
        e.preventDefault();
        // Redirect logic is handled by the global Navbar
    };

    if (loading && products.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full" style={{ minHeight: '400px' }}>
                <Loader2 className="animate-spin text-amazon-orange mb-4" size={48} />
                <p className="text-gray-500 font-medium">Loading products...</p>
            </div>
        );
    }

    return (
        <div className="animate-fade-in">


            <section>
                <div className="flex justify-between items-baseline mb-4">
                    <div className="flex items-baseline gap-2">
                        <h2 className="text-[18px] font-bold text-[#0F1111]">
                            {search ? `Results for "${search}"` : "Discover Products"}
                        </h2>
                        <span className="text-[13px] text-[#565959]">
                            1 - {products.length} of over 1.4 million results
                        </span>
                    </div>
                    <div className="text-[12px] text-[#565959] border border-gray-300 px-2 py-0.5 rounded-sm bg-gray-50 uppercase tracking-tighter">
                        Page {currentPage} of {totalPages}
                    </div>
                </div>

                {error && (
                    <div className="bg-white border border-red-300 text-red-600 p-4 rounded-md mb-8 text-center flex flex-col items-center gap-2">
                        <p className="font-medium">Error: {error}</p>
                        <button onClick={() => window.location.reload()} className="text-amazon-blue hover-underline font-medium">
                            Try Again
                        </button>
                    </div>
                )}

                {products.length === 0 && !loading ? (
                    <div className="empty-state-container animate-fade-in">
                        <div className="text-gray-400 mb-6">
                            <Search size={64} className="mx-auto opacity-10" />
                        </div>
                        <h3 className="text-2xl font-bold text-gray-800 mb-2">No results for "{search}"</h3>
                        <p className="text-gray-500 text-lg">
                            Try checking your spelling or use more general terms
                        </p>
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
                            {products.map(p => (
                                <ProductCard key={p.asin} product={p} />
                            ))}
                        </div>

                        {/* Pagination Footer */}
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
                                    else if (currentPage >= totalPages - 2) pageNum = totalPages - 4 + i;
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
                    </>
                )}
            </section>
        </div>
    );
}
