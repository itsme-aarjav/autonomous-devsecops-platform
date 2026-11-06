import apiClient from './api';
import { Product } from '../types';

// Helper function to get proper image URL
const getImageUrl = (product: any): string => {
  // Backend is now handling image mapping, so just return the image_url as-is
  if (product.image_url) {
    return product.image_url;
  }
  
  // Default fallback
  return '/product-images/placeholder.jpg';
};

export const productService = {
  getAll: async (): Promise<Product[]> => {
    console.log('[ProductService] Fetching products from:', import.meta.env.VITE_API_URL || 'http://localhost:3001/api');
    try {
      const response = await apiClient.get('/products');
      const apiResponse = response.data;
      
      // Transform API response to match frontend types
      if (apiResponse.success && apiResponse.data?.products) {
        console.log('[ProductService] Using wrapped response format');
        return apiResponse.data.products.map((product: any) => {
          return {
            id: product.id,
            name: product.name,
            description: product.description,
            price: parseFloat(product.price),
            originalPrice: product.compare_price ? parseFloat(product.compare_price) : undefined,
            imageUrl: product.image_url,
            category: product.category,
            brand: product.brand,
            inventory: product.inventory_quantity || 0,
            rating: product.rating || 4.5,
            reviewCount: product.reviewCount || Math.floor(Math.random() * 50) + 10,
            isNew: product.is_featured,
            discountPercentage: product.discountPercentage,
            createdAt: product.created_at,
            updatedAt: product.updated_at,
          };
        });
      }
      
      // Fallback for direct array response
      console.log('[ProductService] Using fallback array format');
      return Array.isArray(apiResponse) ? apiResponse.map((product: any) => ({
        id: product.id,
        name: product.name,
        description: product.description,
        price: parseFloat(product.price),
        originalPrice: product.originalPrice ? parseFloat(product.originalPrice) : undefined,
        imageUrl: getImageUrl(product),
        category: product.category || product.category_id,
        brand: product.brand,
        inventory: product.inventory_quantity || product.inventory || 0,
        rating: product.rating,
        reviewCount: product.reviewCount,
        isNew: product.new_arrival,
        discountPercentage: product.discountPercentage,
        createdAt: product.created_at,
        updatedAt: product.updated_at,
      })) : [];
    } catch (error: any) {
      console.warn('[ProductService] Backend products service offline or retired, returning empty catalog');
      return [];
    }
  },

  getById: async (id: string): Promise<Product> => {
    try {
      const response = await apiClient.get(`/products/${id}`);
      const product = response.data.data || response.data;
      
      // Transform API response to match frontend types
      return {
        id: product.id,
        name: product.name,
        description: product.description,
        price: parseFloat(product.price),
        originalPrice: product.originalPrice ? parseFloat(product.originalPrice) : undefined,
        imageUrl: getImageUrl(product),
        category: product.category || product.category_id,
        brand: product.brand,
        inventory: product.inventory_quantity || product.inventory || 0,
        rating: product.rating,
        reviewCount: product.reviewCount,
        isNew: product.new_arrival,
        discountPercentage: product.discountPercentage,
        createdAt: product.created_at,
        updatedAt: product.updated_at,
        images: product.images || [],
      };
    } catch (error: any) {
      console.warn(`[ProductService] Backend products service offline or product ${id} not found`);
      return null as any;
    }
  },

  getByCategory: async (category: string): Promise<Product[]> => {
    try {
      const response = await apiClient.get(`/products?category=${category}`);
      return response.data;
    } catch (error) {
      return [];
    }
  },

  search: async (query: string): Promise<Product[]> => {
    try {
      const response = await apiClient.get(`/products/search?q=${query}`);
      return response.data;
    } catch (error) {
      return [];
    }
  },
};