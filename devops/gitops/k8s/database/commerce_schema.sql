-- Idempotent Commerce Schema Migration for Boutique Platform
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Products Table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    compare_price NUMERIC(10, 2),
    category VARCHAR(50) NOT NULL,
    brand VARCHAR(100) DEFAULT 'Boutique',
    image_url VARCHAR(255) NOT NULL,
    rating NUMERIC(3, 2) DEFAULT 4.80,
    is_featured BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_featured ON products(is_featured);

-- Inventory Table
CREATE TABLE IF NOT EXISTS inventory (
    product_id UUID PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Orders Table
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    total_amount NUMERIC(10, 2) NOT NULL CHECK (total_amount >= 0),
    status VARCHAR(50) NOT NULL DEFAULT 'processing' CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled')),
    shipping_address JSONB NOT NULL,
    payment_method VARCHAR(50) DEFAULT 'DEMO_CHECKOUT',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);

-- Order Items Table
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Idempotent Seed Data for Demo Catalog
INSERT INTO products (id, name, description, price, compare_price, category, brand, image_url, rating, is_featured)
VALUES
    ('11111111-1111-4111-8111-111111111111', 'Cashmere Blend Overcoat', 'Tailored from an exquisite Italian cashmere-wool blend, featuring horn buttons, notched lapels, and a silk lining for refined luxury.', 890.00, 1150.00, 'clothing', 'Maison Boutique', '/product-images/cashmere-coat.jpg', 4.90, true),
    ('22222222-2222-4222-8222-222222222222', 'Silk Evening Gown', 'Floor-length draped gown cut from 100% mulberry silk charmeuse with a subtle cowl neckline and delicate hand-finished hem.', 1250.00, 1500.00, 'clothing', 'Atelier Noir', '/product-images/silk-evening-gown.jpg', 4.95, true),
    ('33333333-3333-4333-8333-333333333333', 'Italian Leather Handbag', 'Handcrafted full-grain Tuscan calfskin with palladium hardware, structured accordion gussets, and detachable crossbody strap.', 650.00, 780.00, 'bags', 'Venezia Pelletteria', '/product-images/leather-handbag.jpg', 4.85, true),
    ('44444444-4444-4444-8444-444444444444', 'Stiletto Designer Heels', '90mm pointed-toe stilettos crafted from Italian patent leather, engineered with ergonomic arch support and leather soles.', 420.00, 510.00, 'shoes', 'Milano Footwear', '/product-images/designer-heels.jpg', 4.75, true),
    ('55555555-5555-4555-8555-555555555555', 'Diamond Solitaire Necklace', 'Brilliant-cut 1.5-carat lab-grown diamond set in an 18-karat white gold bezel on an adjustable 16-18 inch wheat chain.', 2100.00, 2600.00, 'jewelry', 'Lumière Joaillerie', '/product-images/diamond-necklace.jpg', 4.98, true),
    ('66666666-6666-4666-8666-666666666666', 'Classic Tailored Wool Blazer', 'Double-breasted structured blazer in virgin wool with peak lapels, pick-stitching, and mother-of-pearl buttons.', 540.00, 650.00, 'clothing', 'Savile Heritage', '/product-images/cashmere-coat.jpg', 4.80, false),
    ('77777777-7777-4777-8777-777777777777', 'Signature Leather Wallet', 'Slim bi-fold wallet crafted from vegetable-tanned bridle leather with eight card slots, dual note dividers, and RFID blocking.', 195.00, 240.00, 'accessories', 'Venezia Pelletteria', '/product-images/leather-handbag.jpg', 4.70, false),
    ('88888888-8888-4888-8888-888888888888', 'Akoya Pearl Drop Earrings', 'Lustrous Japanese Akoya saltwater cultured pearls suspended from 18-karat yellow gold shepherd hooks.', 380.00, 450.00, 'jewelry', 'Lumière Joaillerie', '/product-images/diamond-necklace.jpg', 4.90, false)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price = EXCLUDED.price,
    compare_price = EXCLUDED.compare_price,
    category = EXCLUDED.category,
    brand = EXCLUDED.brand,
    image_url = EXCLUDED.image_url,
    rating = EXCLUDED.rating,
    is_featured = EXCLUDED.is_featured,
    updated_at = CURRENT_TIMESTAMP;

-- Seed Inventory
INSERT INTO inventory (product_id, quantity)
VALUES
    ('11111111-1111-4111-8111-111111111111', 15),
    ('22222222-2222-4222-8222-222222222222', 8),
    ('33333333-3333-4333-8333-333333333333', 20),
    ('44444444-4444-4444-8444-444444444444', 12),
    ('55555555-5555-4555-8555-555555555555', 5),
    ('66666666-6666-4666-8666-666666666666', 18),
    ('77777777-7777-4777-8777-777777777777', 25),
    ('88888888-8888-4888-8888-888888888888', 14)
ON CONFLICT (product_id) DO NOTHING;
