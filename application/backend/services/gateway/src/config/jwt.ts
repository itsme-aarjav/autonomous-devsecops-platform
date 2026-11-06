export const WEAK_SECRETS = new Set([
  'your-super-secret-jwt-key-here',
  'your-secret-key',
  'your-refresh-secret',
  'secret',
  'jwt-secret',
  'changeme',
  'password',
  '12345678',
  'default',
  'admin',
  'replace_with_a_secure_random_32_plus_char_secret_for_local_dev',
  'replace-with-a-secure-random-32-plus-character-secret-in-production'
]);

export const JWT_ISSUER = 'boutique-auth';
export const JWT_AUDIENCE = 'boutique-microservices';
export const JWT_ALGORITHM = 'HS256';
export const MIN_SECRET_LENGTH = 32;

/**
 * Validates and retrieves the JWT_SECRET from environment variables.
 * In production (NODE_ENV === 'production'):
 *   - Must be explicitly set, non-empty, and non-whitespace.
 *   - Must be at least 32 characters long.
 *   - Must not equal known weak or default placeholder secrets.
 * In non-production (NODE_ENV !== 'production'):
 *   - Must be explicitly set and non-empty (no silent default fallback).
 *   - Logs a security warning if using a weak secret.
 */
export function getValidatedJwtSecret(): string {
  const secret = process.env.JWT_SECRET;
  const isProduction = process.env.NODE_ENV === 'production';

  if (!secret || typeof secret !== 'string' || secret.trim().length === 0) {
    if (isProduction) {
      throw new Error('[FATAL] JWT_SECRET is required and must not be empty in production.');
    }
    throw new Error('[FATAL] JWT_SECRET must be explicitly configured. See .env.example.');
  }

  const trimmed = secret.trim();

  if (isProduction) {
    if (WEAK_SECRETS.has(trimmed.toLowerCase())) {
      throw new Error('[FATAL] Insecure JWT_SECRET detected in production. Default and weak secrets are forbidden.');
    }
    if (trimmed.length < MIN_SECRET_LENGTH) {
      throw new Error(`[FATAL] Insecure JWT_SECRET in production. Minimum length is ${MIN_SECRET_LENGTH} characters.`);
    }
  } else {
    if (WEAK_SECRETS.has(trimmed.toLowerCase())) {
      console.warn('[SECURITY WARNING] Using weak or default JWT_SECRET in non-production mode. Set a strong secret for production.');
    }
  }

  return trimmed;
}

export function getJwtSecret(): string {
  return getValidatedJwtSecret();
}
