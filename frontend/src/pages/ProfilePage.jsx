import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { UserService } from "../services/api";
import ProductCard from "../components/ProductCard";
import { User, Loader2 } from "lucide-react";

export default function ProfilePage() {
  const { userId } = useParams();
  const [profile, setProfile] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [activeTab, setActiveTab] = useState("hybrid");
  const [loading, setLoading] = useState(true);
  const [recsLoading, setRecsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load user profile once
  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await UserService.getProfile(userId);
        setProfile(data);
      } catch (err) {
        console.error("Error fetching profile:", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, [userId]);

  // Load recommendations whenever tab changes
  useEffect(() => {
    const fetchRecs = async () => {
      setRecsLoading(true);
      setRecommendations([]);
      try {
        let data;
        if (activeTab === "hybrid") {
          data = await UserService.getHybridRecommendations(userId, 10);
        } else if (activeTab === "collaborative") {
          data = await UserService.getCollaborativeRecommendations(userId, 10);
        } else {
          data = await UserService.getContentBasedRecommendations(userId, 10);
        }
        setRecommendations(data.products || []);
      } catch (err) {
        console.error("Error fetching recommendations:", err);
      } finally {
        setRecsLoading(false);
      }
    };
    fetchRecs();
  }, [userId, activeTab]);

  if (loading) {
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{ minHeight: "400px" }}
      >
        <Loader2 className="animate-spin text-amazon-orange mb-4" size={48} />
        <p className="text-gray-500 font-medium">Loading profile...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-600">
        <p className="font-medium">Error loading profile: {error}</p>
      </div>
    );
  }

  const user = profile?.user || {};

  return (
    <div style={{ padding: "20px" }}>
      {/* ── Profile Header ── */}
      <div
        className="card"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "20px",
          marginBottom: "30px",
        }}
      >
        <div
          style={{
            width: "80px",
            height: "80px",
            borderRadius: "50%",
            background: "#eee",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <User size={40} color="#aaa" />
        </div>
        <div>
          <h1 style={{ fontSize: "22px", fontWeight: "600", margin: 0 }}>
            {user.name || `User ${userId}`}
          </h1>
          <p style={{ color: "#565959", margin: "4px 0 0" }}>
            User ID: {userId}
            {user.age_group && ` · ${user.age_group}`}
            {user.country && ` · ${user.country}`}
          </p>
          <p style={{ color: "#565959", margin: "2px 0 0", fontSize: "13px" }}>
            {profile?.total_ratings || 0} products rated
          </p>
        </div>
      </div>

      {/* ── Recommendation Tabs ── */}
      <section>
        <h2
          style={{ fontSize: "18px", fontWeight: "700", marginBottom: "12px" }}
        >
          Recommended for you
        </h2>
        <p style={{ marginBottom: "16px", color: "#565959", fontSize: "14px" }}>
          Personalised picks based on your rating history
        </p>

        {/* Tab selector */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
          {[
            { key: "hybrid", label: "Hybrid (Best)" },
            { key: "collaborative", label: "Collaborative" },
            { key: "content", label: "Content-Based" },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: "6px 14px",
                borderRadius: "20px",
                border:
                  activeTab === tab.key
                    ? "2px solid #ff9900"
                    : "1px solid #ccc",
                background: activeTab === tab.key ? "#fff8ee" : "white",
                color: activeTab === tab.key ? "#b56600" : "#555",
                fontWeight: activeTab === tab.key ? "600" : "400",
                cursor: "pointer",
                fontSize: "13px",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {recsLoading ? (
          <div style={{ textAlign: "center", padding: "40px" }}>
            <Loader2
              className="animate-spin"
              size={32}
              style={{ margin: "0 auto", color: "#ff9900" }}
            />
            <p style={{ color: "#565959", marginTop: "12px" }}>
              Computing recommendations...
            </p>
          </div>
        ) : recommendations.length === 0 ? (
          <div
            style={{ textAlign: "center", padding: "40px", color: "#565959" }}
          >
            No personalised recommendations yet. Try rating some products!
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: "16px",
            }}
          >
            {recommendations.map((product) => (
              <ProductCard key={product.asin} product={product} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
