import express from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { query } from '../database/connection';
import { User } from '../types';
import { getJwtSecret, JWT_ISSUER, JWT_AUDIENCE, JWT_ALGORITHM } from '../config/jwt';

const router = express.Router();
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '24h';
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const ALLOWED_DEMO_EMAILS = new Set([
  'customer@boutique.com',
  'demo@boutique.com'
]);

function isDemoLoginPermitted(): boolean {
  // Demo mode is strictly forbidden in production regardless of any other variables
  if (process.env.NODE_ENV === 'production') {
    return false;
  }
  // Requires explicit opt-in via ENABLE_DEMO_LOGIN or ALLOW_DEMO_LOGIN in non-production
  return process.env.ENABLE_DEMO_LOGIN === 'true' || process.env.ALLOW_DEMO_LOGIN === 'true';
}

let currentUser: any = null;

function generateTokens(user: { id: string; email: string; role?: string }) {
  const jwtSecret = getJwtSecret();
  const payload = {
    userId: user.id,
    id: user.id,
    email: user.email,
    role: user.role || 'customer'
  };

  const token = jwt.sign(payload, jwtSecret, {
    algorithm: JWT_ALGORITHM,
    expiresIn: (JWT_EXPIRES_IN as any),
    issuer: JWT_ISSUER,
    audience: JWT_AUDIENCE
  });

  const refreshToken = jwt.sign(
    { userId: user.id, id: user.id, type: 'refresh' },
    jwtSecret,
    {
      algorithm: JWT_ALGORITHM,
      expiresIn: '7d',
      issuer: JWT_ISSUER,
      audience: JWT_AUDIENCE
    }
  );

  return { token, refreshToken };
}

router.post('/register', async (req, res) => {
  try {
    const { email, password, firstName, lastName } = req.body;

    const existingUser = await query('SELECT id FROM users WHERE email = $1', [email]);
    if (existingUser.rows.length > 0) {
      return res.status(400).json({ error: 'User already exists' });
    }

    const hashedPassword = await bcrypt.hash(password, 10);
    const result = await query(
      'INSERT INTO users (email, password_hash, first_name, last_name, role) VALUES ($1, $2, $3, $4, $5) RETURNING id, email, first_name, last_name, role, created_at, updated_at',
      [email, hashedPassword, firstName, lastName, 'customer']
    );

    const user = result.rows[0];
    currentUser = {
      id: user.id,
      email: user.email,
      firstName: user.first_name,
      lastName: user.last_name,
      role: user.role
    };

    const { token, refreshToken } = generateTokens(user);

    res.status(201).json({
      user: {
        id: user.id,
        email: user.email,
        firstName: user.first_name,
        lastName: user.last_name,
        role: user.role,
        createdAt: user.created_at,
        updatedAt: user.updated_at
      },
      token,
      refreshToken,
      message: 'Registration successful'
    });
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Registration failed' });
  }
});

router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;

    // Demo mode: strictly opt-in in development/test, forbidden in production, and restricted to allowed demo emails
    if (isDemoLoginPermitted() && password === 'demo' && ALLOWED_DEMO_EMAILS.has(email?.toLowerCase())) {
      let user;
      const result = await query('SELECT id, email, first_name, last_name, role, created_at, updated_at FROM users WHERE email = $1', [email]);

      if (result.rows.length === 0) {
        // Create demo user if doesn't exist
        const hashedPassword = await bcrypt.hash('demo', 10);
        const newUser = await query(
          'INSERT INTO users (email, password_hash, first_name, last_name, role) VALUES ($1, $2, $3, $4, $5) RETURNING id, email, first_name, last_name, role, created_at, updated_at',
          [email, hashedPassword, 'Demo', 'User', 'customer']
        );
        user = newUser.rows[0];
      } else {
        user = result.rows[0];
      }

      currentUser = {
        id: user.id,
        email: user.email,
        firstName: user.first_name,
        lastName: user.last_name,
        role: user.role
      };

      const { token, refreshToken } = generateTokens(user);

      res.json({
        user: {
          id: user.id,
          email: user.email,
          firstName: user.first_name,
          lastName: user.last_name,
          role: user.role,
          createdAt: user.created_at,
          updatedAt: user.updated_at
        },
        token,
        refreshToken,
        message: 'Demo login successful'
      });
      return;
    }

    // Normal password check
    const result = await query('SELECT id, email, password_hash, first_name, last_name, role, created_at, updated_at FROM users WHERE email = $1', [email]);

    if (result.rows.length === 0) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const user = result.rows[0];
    const isValidPassword = await bcrypt.compare(password, user.password_hash);

    if (!isValidPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    currentUser = {
      id: user.id,
      email: user.email,
      firstName: user.first_name,
      lastName: user.last_name,
      role: user.role
    };

    const { token, refreshToken } = generateTokens(user);

    res.json({
      user: {
        id: user.id,
        email: user.email,
        firstName: user.first_name,
        lastName: user.last_name,
        role: user.role,
        createdAt: user.created_at,
        updatedAt: user.updated_at
      },
      token,
      refreshToken,
      message: 'Login successful'
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Login failed' });
  }
});

router.post('/refresh', async (req, res) => {
  try {
    const { refreshToken } = req.body;
    if (!refreshToken) {
      return res.status(400).json({ error: 'Refresh token required' });
    }
    const decoded = jwt.verify(refreshToken, getJwtSecret(), {
      algorithms: [JWT_ALGORITHM],
      issuer: JWT_ISSUER,
      audience: JWT_AUDIENCE
    }) as any;

    if (decoded.type !== 'refresh') {
      return res.status(401).json({ error: 'Invalid token: not a refresh token' });
    }

    const userId = decoded.userId || decoded.id;
    if (!userId || !UUID_REGEX.test(userId)) {
      return res.status(401).json({ error: 'Invalid token payload: missing valid user ID' });
    }

    // Fetch the current user from the database to ensure user exists and obtain current claims
    const result = await query(
      'SELECT id, email, first_name, last_name, role FROM users WHERE id = $1',
      [userId]
    );

    if (result.rows.length === 0) {
      return res.status(401).json({ error: 'User no longer exists' });
    }

    const user = result.rows[0];

    const { token } = generateTokens({
      id: user.id,
      email: user.email,
      role: user.role || 'customer'
    });

    return res.json({ token });
  } catch (err: any) {
    return res.status(401).json({ error: 'Invalid or expired refresh token' });
  }
});

router.post('/logout', (req, res) => {
  currentUser = null;
  res.json({ message: 'Logged out successfully' });
});

router.get('/me', async (req, res) => {
  const authHeader = req.headers.authorization;
  const token = authHeader?.startsWith('Bearer ') ? authHeader.split(' ')[1] : null;

  if (!token || token === 'undefined') {
    return res.status(401).json({ error: 'Not logged in' });
  }

  try {
    let targetUserId: string;

    if (token.includes('.')) {
      // Cryptographic JWT verification
      const decoded = jwt.verify(token, getJwtSecret(), {
        algorithms: [JWT_ALGORITHM],
        issuer: JWT_ISSUER,
        audience: JWT_AUDIENCE
      }) as any;

      targetUserId = decoded.userId || decoded.id;
    } else if (process.env.NODE_ENV !== 'production' && UUID_REGEX.test(token)) {
      // Development mode fallback for raw UUID token (strictly disabled in production)
      targetUserId = token;
    } else {
      return res.status(401).json({ error: 'Invalid token format' });
    }

    const result = await query(
      'SELECT id, email, first_name, last_name, role FROM users WHERE id = $1',
      [targetUserId]
    );
    if (result.rows.length === 0) {
      return res.status(401).json({ error: 'User not found' });
    }
    const user = result.rows[0];
    res.json({
      id: user.id,
      email: user.email,
      firstName: user.first_name,
      lastName: user.last_name,
      role: user.role
    });
  } catch (error: any) {
    console.warn('Authentication error:', error.message);
    res.status(401).json({ error: 'Invalid or expired token', details: error.message });
  }
});

export { router as authRoutes };
