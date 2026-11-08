import { Router, Request, Response } from 'express';
import { query } from '../database/connection';

const router = Router();

// Helper to format product row
function formatProduct(row: any) {
  return {
    id: row.id,
    name: row.name,
    description: row.description,
    price: parseFloat(row.price),
    compare_price: row.compare_price ? parseFloat(row.compare_price) : undefined,
    category: row.category,
    brand: row.brand || 'Boutique',
    image_url: row.image_url,
    rating: row.rating !== null && row.rating !== undefined ? parseFloat(row.rating) : undefined,
    is_featured: Boolean(row.is_featured),
    inventory_quantity: row.quantity !== null && row.quantity !== undefined ? parseInt(row.quantity, 10) : 0,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

// GET /products - List all products with optional filters
router.get('/', async (req: Request, res: Response) => {
  try {
    const { category, search, q, featured } = req.query;
    const filterQuery = (search || q) as string | undefined;

    let sql = `
      SELECT p.*, COALESCE(i.quantity, 0) as quantity
      FROM products p
      LEFT JOIN inventory i ON p.id = i.product_id
      WHERE 1=1
    `;
    const params: any[] = [];

    if (category && typeof category === 'string' && category.trim() !== '') {
      params.push(category.trim().toLowerCase());
      sql += ` AND LOWER(p.category) = $${params.length}`;
    }

    if (filterQuery && filterQuery.trim() !== '') {
      params.push(`%${filterQuery.trim()}%`);
      sql += ` AND (p.name ILIKE $${params.length} OR p.description ILIKE $${params.length})`;
    }

    if (featured === 'true' || featured === '1') {
      sql += ` AND p.is_featured = true`;
    }

    sql += ` ORDER BY p.is_featured DESC, p.created_at DESC`;

    const result = await query(sql, params);
    const products = result.rows.map(formatProduct);

    return res.json({
      success: true,
      data: {
        products,
        total: products.length,
      },
    });
  } catch (error: any) {
    console.error('[Products API] Failed to fetch products:', error);
    return res.status(500).json({ success: false, error: 'Failed to retrieve products' });
  }
});

// GET /products/search - Dedicated search endpoint
router.get('/search', async (req: Request, res: Response) => {
  try {
    const searchQuery = (req.query.q || req.query.query || '') as string;
    if (!searchQuery.trim()) {
      return res.json({ success: true, data: { products: [] } });
    }

    const sql = `
      SELECT p.*, COALESCE(i.quantity, 0) as quantity
      FROM products p
      LEFT JOIN inventory i ON p.id = i.product_id
      WHERE p.name ILIKE $1 OR p.description ILIKE $1 OR p.category ILIKE $1
      ORDER BY p.price DESC
    `;
    const result = await query(sql, [`%${searchQuery.trim()}%`]);
    const products = result.rows.map(formatProduct);

    return res.json({
      success: true,
      data: {
        products,
        total: products.length,
      },
    });
  } catch (error: any) {
    console.error('[Products API] Search failed:', error);
    return res.status(500).json({ success: false, error: 'Product search failed' });
  }
});

// GET /products/:id - Single product details
router.get('/:id', async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const sql = `
      SELECT p.*, COALESCE(i.quantity, 0) as quantity
      FROM products p
      LEFT JOIN inventory i ON p.id = i.product_id
      WHERE p.id = $1
    `;
    const result = await query(sql, [id]);

    if (result.rows.length === 0) {
      return res.status(404).json({ success: false, error: `Product not found with id ${id}` });
    }

    const product = formatProduct(result.rows[0]);
    return res.json({
      success: true,
      data: product,
    });
  } catch (error: any) {
    console.error(`[Products API] Failed to fetch product ${req.params.id}:`, error);
    return res.status(500).json({ success: false, error: 'Failed to retrieve product details' });
  }
});

export const productRoutes = router;
