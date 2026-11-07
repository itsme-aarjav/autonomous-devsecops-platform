import { Router, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import { getPool, query } from '../database/connection';
import { getValidatedJwtSecret } from '../config/jwt';

const router = Router();
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Authentication helper
interface AuthenticatedUser {
  id: string;
  email?: string;
  role: string;
}

function extractUser(req: Request): AuthenticatedUser | null {
  // 1. Check identity forwarded securely by API Gateway
  const gatewayUserId = req.headers['x-user-id'] as string;
  if (gatewayUserId && UUID_REGEX.test(gatewayUserId)) {
    return {
      id: gatewayUserId,
      email: (req.headers['x-user-email'] as string) || '',
      role: (req.headers['x-user-role'] as string) || 'customer',
    };
  }

  // 2. Direct Bearer token validation (defense-in-depth)
  const authHeader = req.headers.authorization;
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.substring(7).trim();
    try {
      const decoded = jwt.verify(token, getValidatedJwtSecret()) as any;
      const userId = decoded.userId || decoded.id;
      if (userId && UUID_REGEX.test(userId)) {
        return {
          id: userId,
          email: decoded.email || '',
          role: decoded.role || 'customer',
        };
      }
    } catch (err: any) {
      // Invalid token
    }
  }

  return null;
}

// POST /orders - Place an order with transactional inventory deduction & price verification
router.post('/', async (req: Request, res: Response) => {
  const user = extractUser(req);
  if (!user) {
    return res.status(401).json({ error: 'Unauthorized: Authentication required to place orders' });
  }

  const { items, shippingAddress } = req.body;

  if (!Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ error: 'Invalid order: items must be a non-empty array' });
  }

  if (!shippingAddress || typeof shippingAddress !== 'object') {
    return res.status(400).json({ error: 'Invalid order: shippingAddress is required' });
  }

  for (const item of items) {
    const prodId = item.productId || item.id;
    const qty = parseInt(item.quantity, 10);
    if (!prodId || !UUID_REGEX.test(prodId)) {
      return res.status(400).json({ error: `Invalid productId: ${prodId}` });
    }
    if (isNaN(qty) || qty <= 0) {
      return res.status(400).json({ error: `Invalid quantity for product ${prodId}: must be positive integer` });
    }
  }

  const pool = getPool();
  const client = await pool.connect();

  try {
    await client.query('BEGIN');

    let subtotal = 0;
    const verifiedItems: Array<{
      productId: string;
      quantity: number;
      price: number;
      product: any;
    }> = [];

    // Verify each item's price and inventory inside transaction
    for (const item of items) {
      const prodId = item.productId || item.id;
      const requestedQty = parseInt(item.quantity, 10);

      // 1. Fetch real product price
      const prodResult = await client.query(
        'SELECT id, name, description, price, compare_price, category, brand, image_url, rating FROM products WHERE id = $1',
        [prodId]
      );

      if (prodResult.rows.length === 0) {
        await client.query('ROLLBACK');
        return res.status(400).json({ error: `Product not found: ${prodId}` });
      }

      const product = prodResult.rows[0];
      const verifiedPrice = parseFloat(product.price);

      // 2. Lock and verify inventory
      const invResult = await client.query(
        'SELECT quantity FROM inventory WHERE product_id = $1 FOR UPDATE',
        [prodId]
      );

      if (invResult.rows.length === 0) {
        await client.query('ROLLBACK');
        return res.status(400).json({ error: `Inventory not configured for product: ${product.name}` });
      }

      const availableQty = invResult.rows[0].quantity;
      if (availableQty < requestedQty) {
        await client.query('ROLLBACK');
        return res.status(400).json({
          error: `Insufficient inventory for ${product.name}. Available: ${availableQty}, requested: ${requestedQty}`,
        });
      }

      // 3. Atomically decrement inventory
      await client.query(
        'UPDATE inventory SET quantity = quantity - $1, updated_at = CURRENT_TIMESTAMP WHERE product_id = $2',
        [requestedQty, prodId]
      );

      subtotal += verifiedPrice * requestedQty;
      verifiedItems.push({
        productId: prodId,
        quantity: requestedQty,
        price: verifiedPrice,
        product: {
          id: product.id,
          name: product.name,
          description: product.description,
          price: verifiedPrice,
          originalPrice: product.compare_price ? parseFloat(product.compare_price) : undefined,
          imageUrl: product.image_url,
          category: product.category,
          brand: product.brand,
          rating: parseFloat(product.rating || '4.8'),
        },
      });
    }

    // Server-side tax & shipping calculation
    const shipping = subtotal > 500 ? 0 : 15.0;
    const tax = Math.round(subtotal * 0.08 * 100) / 100;
    const totalAmount = Math.round((subtotal + shipping + tax) * 100) / 100;

    // 4. Create Order
    const orderResult = await client.query(
      `INSERT INTO orders (user_id, total_amount, status, shipping_address, payment_method)
       VALUES ($1, $2, 'processing', $3, 'DEMO_CHECKOUT')
       RETURNING id, user_id, total_amount, status, shipping_address, created_at, updated_at`,
      [user.id, totalAmount, JSON.stringify(shippingAddress)]
    );

    const orderRow = orderResult.rows[0];
    const orderId = orderRow.id;

    // 5. Create Order Items
    const createdItems: any[] = [];
    for (const vItem of verifiedItems) {
      const itemResult = await client.query(
        `INSERT INTO order_items (order_id, product_id, quantity, price)
         VALUES ($1, $2, $3, $4)
         RETURNING id`,
        [orderId, vItem.productId, vItem.quantity, vItem.price]
      );

      createdItems.push({
        id: itemResult.rows[0].id,
        productId: vItem.productId,
        quantity: vItem.quantity,
        price: vItem.price,
        product: vItem.product,
      });
    }

    await client.query('COMMIT');

    const createdOrder = {
      id: orderId,
      userId: orderRow.user_id,
      items: createdItems,
      totalAmount: parseFloat(orderRow.total_amount),
      status: orderRow.status,
      shippingAddress: typeof orderRow.shipping_address === 'string'
        ? JSON.parse(orderRow.shipping_address)
        : orderRow.shipping_address,
      createdAt: orderRow.created_at,
      updatedAt: orderRow.updated_at,
    };

    console.log(`[Orders API] Created demo order ${orderId} for user ${user.id} ($${totalAmount})`);
    return res.status(201).json(createdOrder);
  } catch (error: any) {
    await client.query('ROLLBACK');
    console.error('[Orders API] Order placement failed:', error);
    return res.status(500).json({ error: 'Order transaction failed' });
  } finally {
    client.release();
  }
});

// GET /orders/my-orders - Retrieve all orders for authenticated customer
router.get('/my-orders', async (req: Request, res: Response) => {
  const user = extractUser(req);
  if (!user) {
    return res.status(401).json({ error: 'Unauthorized: Authentication required to view order history' });
  }

  try {
    const ordersResult = await query(
      `SELECT o.* 
       FROM orders o 
       WHERE o.user_id = $1 
       ORDER BY o.created_at DESC`,
      [user.id]
    );

    if (ordersResult.rows.length === 0) {
      return res.json([]);
    }

    const orderIds = ordersResult.rows.map((r: any) => r.id);
    const itemsResult = await query(
      `SELECT oi.*, p.name, p.description, p.category, p.brand, p.image_url, p.rating
       FROM order_items oi
       JOIN products p ON oi.product_id = p.id
       WHERE oi.order_id = ANY($1::uuid[])`,
      [orderIds]
    );

    const itemsByOrder: Record<string, any[]> = {};
    for (const itemRow of itemsResult.rows) {
      if (!itemsByOrder[itemRow.order_id]) {
        itemsByOrder[itemRow.order_id] = [];
      }
      itemsByOrder[itemRow.order_id].push({
        id: itemRow.id,
        productId: itemRow.product_id,
        quantity: itemRow.quantity,
        price: parseFloat(itemRow.price),
        product: {
          id: itemRow.product_id,
          name: itemRow.name,
          description: itemRow.description,
          price: parseFloat(itemRow.price),
          imageUrl: itemRow.image_url,
          category: itemRow.category,
          brand: itemRow.brand,
          rating: parseFloat(itemRow.rating || '4.8'),
        },
      });
    }

    const orders = ordersResult.rows.map((row: any) => ({
      id: row.id,
      userId: row.user_id,
      items: itemsByOrder[row.id] || [],
      totalAmount: parseFloat(row.total_amount),
      status: row.status,
      shippingAddress: typeof row.shipping_address === 'string'
        ? JSON.parse(row.shipping_address)
        : row.shipping_address,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    }));

    return res.json(orders);
  } catch (error: any) {
    console.error('[Orders API] Failed to fetch customer orders:', error);
    return res.status(500).json({ error: 'Failed to retrieve orders' });
  }
});

// GET /orders/:id - Single order with strict ownership authorization
router.get('/:id', async (req: Request, res: Response) => {
  const user = extractUser(req);
  if (!user) {
    return res.status(401).json({ error: 'Unauthorized: Authentication required' });
  }

  const { id } = req.params;
  if (!UUID_REGEX.test(id)) {
    return res.status(400).json({ error: 'Invalid order ID format' });
  }

  try {
    const orderResult = await query('SELECT * FROM orders WHERE id = $1', [id]);
    if (orderResult.rows.length === 0) {
      return res.status(404).json({ error: 'Order not found' });
    }

    const orderRow = orderResult.rows[0];

    // Strict Ownership Authorization
    if (orderRow.user_id !== user.id && user.role !== 'admin') {
      return res.status(403).json({ error: 'Forbidden: You do not have permission to view this order' });
    }

    const itemsResult = await query(
      `SELECT oi.*, p.name, p.description, p.category, p.brand, p.image_url, p.rating
       FROM order_items oi
       JOIN products p ON oi.product_id = p.id
       WHERE oi.order_id = $1`,
      [id]
    );

    const items = itemsResult.rows.map((itemRow: any) => ({
      id: itemRow.id,
      productId: itemRow.product_id,
      quantity: itemRow.quantity,
      price: parseFloat(itemRow.price),
      product: {
        id: itemRow.product_id,
        name: itemRow.name,
        description: itemRow.description,
        price: parseFloat(itemRow.price),
        imageUrl: itemRow.image_url,
        category: itemRow.category,
        brand: itemRow.brand,
        rating: parseFloat(itemRow.rating || '4.8'),
      },
    }));

    const order = {
      id: orderRow.id,
      userId: orderRow.user_id,
      items,
      totalAmount: parseFloat(orderRow.total_amount),
      status: orderRow.status,
      shippingAddress: typeof orderRow.shipping_address === 'string'
        ? JSON.parse(orderRow.shipping_address)
        : orderRow.shipping_address,
      createdAt: orderRow.created_at,
      updatedAt: orderRow.updated_at,
    };

    return res.json(order);
  } catch (error: any) {
    console.error(`[Orders API] Failed to fetch order ${id}:`, error);
    return res.status(500).json({ error: 'Failed to retrieve order' });
  }
});

export const orderRoutes = router;
