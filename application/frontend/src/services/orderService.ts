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
    } catch (error) {
      console.warn('[OrderService] Backend orders service offline or retired');
      throw error;
    }
  },

  getUserOrders: async (): Promise<Order[]> => {
    try {
      const response = await apiClient.get('/orders/my-orders');
      return response.data;
    } catch (error) {
      console.warn('[OrderService] Backend orders service offline or retired, returning empty list');
      return [];
    }
  },

  getOrderById: async (id: string): Promise<Order> => {
    try {
      const response = await apiClient.get(`/orders/${id}`);
      return response.data;
    } catch (error) {
      console.warn(`[OrderService] Backend orders service offline or order ${id} not found`);
      return null as any;
    }
  },

  updateOrderStatus: async (id: string, status: string): Promise<Order> => {
    try {
      const response = await apiClient.patch(`/orders/${id}/status`, { status });
      return response.data;
    } catch (error) {
      console.warn(`[OrderService] Backend orders service offline or order ${id} update failed`);
      throw error;
    }
  },
};