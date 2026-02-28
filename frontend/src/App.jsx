import { BrowserRouter as Router, Routes, Route, Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { Search, ShoppingCart, Menu, User } from "lucide-react";
import HomePage from "./pages/HomePage";
import ProductDetailPage from "./pages/ProductDetailPage";
import ProfilePage from "./pages/ProfilePage";

function Navbar() {
    const [searchTerm, setSearchTerm] = useState("");
    const navigate = useNavigate();

    const handleSearch = (e) => {
        e.preventDefault();
        if (searchTerm.trim()) {
            navigate(`/?search=${encodeURIComponent(searchTerm)}`);
        } else {
            navigate("/");
        }
    };

    return (
        <nav style={{ background: "var(--amazon-nav-bg)", color: "white", padding: "10px 20px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "20px", maxWidth: "1500px", margin: "0 auto" }}>

                {/* Logo Area */}
                <Link to="/" style={{ color: "white", display: "flex", alignItems: "center", gap: "5px", textDecoration: "none" }}>
                    <h1 style={{ fontSize: "24px", margin: 0, fontWeight: "bold" }}>e commerce<span style={{ color: "var(--amazon-orange)" }}> engine</span></h1>
                </Link>

                {/* Search Bar - Flex Grow */}
                <form onSubmit={handleSearch} style={{ flex: 1, display: "flex", height: "40px" }}>
                    <select style={{ background: "#f3f3f3", border: "none", borderRadius: "4px 0 0 4px", padding: "0 10px", outline: "none", cursor: "pointer" }}>
                        <option>All</option>
                    </select>
                    <input
                        type="text"
                        placeholder="Search E Commerce Engine"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{ flex: 1, padding: "0 15px", border: "none", outline: "none" }}
                    />
                    <button type="submit" style={{ background: "var(--amazon-orange)", border: "none", borderRadius: "0 4px 4px 0", width: "45px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <Search size={20} color="#111" />
                    </button>
                </form>

                {/* Right Nav Links */}
                <div style={{ display: "flex", alignItems: "center", gap: "15px" }}>
                    <Link to="/profile/1" style={{ color: "white", textDecoration: "none", display: "flex", flexDirection: "column" }}>
                        <span style={{ fontSize: "12px", color: "#ccc" }}>Hello, User</span>
                        <span style={{ fontWeight: "bold", display: "flex", alignItems: "center", gap: "2px" }}>Account & Lists <User size={16} /></span>
                    </Link>
                    <div style={{ color: "white", textDecoration: "none", display: "flex", flexDirection: "column", cursor: "pointer" }}>
                        <span style={{ fontSize: "12px", color: "#ccc" }}>Returns</span>
                        <span style={{ fontWeight: "bold" }}>& Orders</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "5px", fontWeight: "bold", cursor: "pointer" }}>
                        <ShoppingCart size={28} />
                        Cart
                    </div>
                </div>

            </div>

            {/* Subnav */}
            <div style={{ display: "flex", alignItems: "center", gap: "15px", marginTop: "10px", fontSize: "14px", maxWidth: "1500px", margin: "10px auto 0 auto" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "5px", cursor: "pointer", fontWeight: "bold" }}>
                    <Menu size={18} /> All
                </div>
                <div style={{ cursor: "pointer" }}>Today's Deals</div>
                <div style={{ cursor: "pointer" }}>Customer Service</div>
                <div style={{ cursor: "pointer" }}>Registry</div>
                <div style={{ cursor: "pointer" }}>Gift Cards</div>
                <div style={{ cursor: "pointer" }}>Sell</div>
            </div>
        </nav>
    );
}

function App() {
    return (
        <Router>
            <div className="app-container">
                <Navbar />
                <main className="main-content">
                    <Routes>
                        <Route path="/" element={<HomePage />} />
                        <Route path="/product/:asin" element={<ProductDetailPage />} />
                        {/* Hardcoded to user 1 for demo based on db struct */}
                        <Route path="/profile/:userId" element={<ProfilePage />} />
                    </Routes>
                </main>
            </div>
        </Router>
    );
}

export default App;
