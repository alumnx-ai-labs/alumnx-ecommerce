const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const ProductService = {
  getProducts: async (page = 1, limit = 20, categoryId = null) => {
    let url = `${API_BASE}/products?page=${page}&limit=${limit}`;
    if (categoryId) url += `&category_id=${categoryId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch products");
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
