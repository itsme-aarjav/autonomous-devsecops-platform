import apiClient from './api';
import { Order } from '../types';

export const orderService = {
  createOrder: async (orderData: {
    items: { productId: string; quantity: number }[];
    shippingAddress: any;
  }): Promise<Order> => {
    try {
      const response = await apiClient.post('/orders', orderData);
      return response.data;
    } catch (error: any) {
      console.error('[OrderService] Failed to create order:', error.message || error);
      throw error;
    }
  },

  getUserOrders: async (): Promise<Order[]> => {
    try {
      const response = await apiClient.get('/orders/my-orders');
      return response.data;
    } catch (error: any) {
      console.error('[OrderService] Failed to fetch orders:', error.message || error);
      return [];
    }
  },

  getOrderById: async (id: string): Promise<Order> => {
    try {
      const response = await apiClient.get(`/orders/${id}`);
      return response.data;
    } catch (error: any) {
      console.error(`[OrderService] Failed to fetch order ${id}:`, error.message || error);
      return null as any;
    }
  },

  updateOrderStatus: async (id: string, status: string): Promise<Order> => {
    try {
      const response = await apiClient.patch(`/orders/${id}/status`, { status });
      return response.data;
    } catch (error: any) {
      console.error(`[OrderService] Failed to update order ${id} status:`, error.message || error);
      throw error;
    }
  },
};