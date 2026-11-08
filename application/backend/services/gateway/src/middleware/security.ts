import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { getJwtSecret, JWT_ISSUER, JWT_AUDIENCE, JWT_ALGORITHM } from '../config/jwt';

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Gateway Security Middleware:
 * Strips untrusted client identity headers and injects verified identity
 * only after cryptographic verification of Authorization JWT or trusted dev fallback.
 */
export function gatewaySecurityMiddleware(req: any, res: any, next: NextFunction) {
  // 1. Strip untrusted client headers immediately
  delete req.headers['x-user-id'];
  delete req.headers['x-user-role'];
  delete req.headers['x-user-email'];

  // 2. Cryptographic JWT validation if Authorization header is provided
  const authHeader = req.headers.authorization;
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.substring(7).trim();
    if (token.includes('.')) {
      try {
        const decoded = jwt.verify(token, getJwtSecret(), {
          algorithms: [JWT_ALGORITHM],
          issuer: JWT_ISSUER,
          audience: JWT_AUDIENCE
        }) as any;

        const userId = decoded.userId || decoded.id;
        if (userId && UUID_REGEX.test(userId)) {
          req.user = {
            id: userId,
            role: decoded.role || 'customer',
            email: decoded.email || ''
          };
          req.headers['x-user-id'] = userId;
          req.headers['x-user-role'] = decoded.role || 'customer';
          if (decoded.email) {
            req.headers['x-user-email'] = decoded.email;
          }
        }
      } catch (err: any) {
        // Token invalid, expired, or forged: leave headers stripped
        console.warn(`[Gateway Security] JWT verification failed: ${err.message}`);
      }
    } else if (process.env.NODE_ENV !== 'production' && UUID_REGEX.test(token)) {
      // Local development/demo fallback: raw UUID token
      req.user = { id: token, role: 'customer' };
      req.headers['x-user-id'] = token;
      req.headers['x-user-role'] = 'customer';
    }
  }

  next();
}
