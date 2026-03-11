const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8005";

export const ProductService = {
  getProducts: async (page = 1, limit = 20, categoryId = null) => {
    let url = `${API_BASE}/products?page=${page}&limit=${limit}`;
    if (categoryId) url += `&category_id=${categoryId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch products");
    return res.json();
  },

  searchProducts: async (query, limit = 10) => {
    const res = await fetch(`${API_BASE}/products/search?query=${encodeURIComponent(query)}&limit=${limit}`);
    if (!res.ok) throw new Error("Semantic search failed");
    return res.json();
  },

  getProduct: async (asin) => {
    const res = await fetch(`${API_BASE}/products/${asin}`);
    if (!res.ok) throw new Error("Product not found");
    return res.json();
  },

  createProduct: async (product) => {
    const res = await fetch(`${API_BASE}/products`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to create product");
    }
    return res.json();
  },

  updateProduct: async (asin, product) => {
    const res = await fetch(`${API_BASE}/products/${asin}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product),
    });
    if (!res.ok) throw new Error("Failed to update product");
    return res.json();
  },

  deleteProduct: async (asin) => {
    const res = await fetch(`${API_BASE}/products/${asin}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete product");
    return res.json();
  },

  getCategories: async () => {
    const res = await fetch(`${API_BASE}/categories`);
    if (!res.ok) throw new Error("Failed to fetch categories");
    return res.json();
  },

  getStats: async () => {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) throw new Error("Failed to fetch stats");
    return res.json();
  },
};

const AI_BASE = import.meta.env.VITE_AI_SERVER_URL || "http://127.0.0.1:8006";

export const AIService = {
  chat: async (message) => {
    const res = await fetch(`${AI_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) throw new Error("Failed to chat with AI");
    return res.json();
  },

  embedDescription: async (productId, description) => {
    const res = await fetch(`${AI_BASE}/embed-description`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId, description }),
    });
    if (!res.ok) throw new Error("Failed to embed product description");
    return res.json();
  }
};
