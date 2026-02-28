import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import ProductCard from "../components/ProductCard";
import { User } from "lucide-react";

const API_BASE = "http://localhost:8000/api";

export default function ProfilePage() {
    const { userId } = useParams();
    const [recommendations, setRecommendations] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchRecs = async () => {
            setLoading(true);
            try {
                const res = await axios.get(`${API_BASE}/users/${userId}/recommendations`);
                setRecommendations(res.data || []);
            } catch (err) {
                console.error("Error fetching recommendations:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchRecs();
    }, [userId]);

    return (
        <div>
            <div className="card" style={{ display: "flex", alignItems: "center", gap: "20px", marginBottom: "40px" }}>
                <div style={{ width: "80px", height: "80px", borderRadius: "50%", background: "#eee", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <User size={40} color="#aaa" />
                </div>
                <div>
                    <h1 style={{ fontSize: "28px", fontWeight: "500" }}>Your Account</h1>
                    <p style={{ color: "#565959" }}>User ID: {userId} • Member</p>
                </div>
            </div>

            <section>
                <h2 className="section-title">Recommended for you</h2>
                <p style={{ marginBottom: "20px", color: "#565959" }}>Inspired by your browsing and rating history</p>

                {loading ? (
                    <div>Loading recommendations...</div>
                ) : recommendations.length === 0 ? (
                    <div>No personalized recommendations available yet. Try rating some products!</div>
                ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: "20px" }}>
                        {recommendations.map(r => r.product && (
                            <ProductCard key={r.product_id} product={r.product} />
                        ))}
                    </div>
                )}
            </section>
        </div>
    );
}
