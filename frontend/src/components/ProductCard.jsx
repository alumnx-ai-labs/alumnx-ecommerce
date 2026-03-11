import { Link } from "react-router-dom";
import { Star } from "lucide-react";

export default function ProductCard({ product }) {
    // Amazon characteristic colors
    const amazonOrange = "#FFA41C";
    const amazonLinkColor = "#007185";
    const amazonPriceColor = "#0F1111";

    return (
        <div className="group flex flex-col bg-white border border-gray-200 rounded-md overflow-hidden hover:shadow-lg transition-all duration-200 h-full p-4">
            {/* Image Section - Consistent height with fixed aspect ratio */}
            <Link to={`/product/${product.asin}`} className="relative h-48 w-full mb-4 flex items-center justify-center overflow-hidden">
                {product.imgUrl ? (
                    <img
                        src={product.imgUrl}
                        alt={product.title}
                        className="max-h-full max-w-full object-contain transition-transform duration-300 group-hover:scale-105"
                        onError={(e) => { e.target.src = 'https://via.placeholder.com/200x200?text=No+Image'; }}
                    />
                ) : (
                    <div className="text-gray-300 font-medium">No Image</div>
                )}
                
                {product.isBestSeller && (
                    <div className="absolute top-0 left-0 bg-[#e47911] text-white text-[10px] font-bold px-2 py-0.5 shadow-sm uppercase">
                        Best Seller
                    </div>
                )}
            </Link>

            {/* Content Section */}
            <div className="flex flex-col flex-1">
                {/* Product Title */}
                <Link 
                    to={`/product/${product.asin}`} 
                    className="text-[14px] leading-tight text-[#0F1111] font-medium h-10 overflow-hidden line-clamp-2 mb-1 hover:text-[#C45500] no-underline"
                >
                    {product.title}
                </Link>

                {/* Ratings Row */}
                <div className="flex items-center gap-1 mb-2">
                    <div className="flex" style={{ color: amazonOrange }}>
                        {[...Array(5)].map((_, i) => (
                            <Star 
                                key={i} 
                                size={14} 
                                fill={i < Math.round(product.stars || 0) ? "currentColor" : "none"} 
                                strokeWidth={1}
                                className={i < Math.round(product.stars || 0) ? "" : "text-gray-200"}
                            />
                        ))}
                    </div>
                    <span className="text-[12px] text-[#007185] hover:text-[#C45500] cursor-pointer">
                        {product.reviews?.toLocaleString() || 0}
                    </span>
                </div>

                {/* Price Display */}
                <div className="flex items-start mb-1">
                    <span className="text-[13px] text-[#0F1111] mt-0.5 font-medium">$</span>
                    <span className="text-[28px] leading-none text-[#0F1111] font-medium">
                        {Math.floor(product.price || 0)}
                    </span>
                    <span className="text-[13px] text-[#0F1111] mt-0.5 font-medium">
                        {((product.price || 0) % 1).toFixed(2).substring(2)}
                    </span>
                </div>

                {/* Shipping Info */}
                <div className="text-[12px] text-[#565959] mb-4">
                    <span className="font-medium text-[#007185]">FREE Delivery</span> by Amazon
                </div>

                {/* Action Button - Locked to bottom */}
                <div className="mt-auto pt-2">
                    <button 
                        onClick={(e) => { 
                            e.preventDefault(); 
                            e.stopPropagation();
                            alert("Added to cart!"); 
                        }}
                        className="w-full bg-[#FFD814] hover:bg-[#F7CA00] border border-[#FCD200] rounded-full py-1.5 px-3 text-[12px] font-medium text-[#0F1111] shadow-sm transition-colors active:shadow-inner"
                    >
                        Add to Cart
                    </button>
                </div>
            </div>
        </div>
    );
}
