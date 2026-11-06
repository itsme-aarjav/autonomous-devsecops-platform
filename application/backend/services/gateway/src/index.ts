import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import jwt from 'jsonwebtoken';
import { createProxyMiddleware } from 'http-proxy-middleware';
import dotenv from 'dotenv';
import { metricsMiddleware, setupMetrics } from './metrics';
import { getValidatedJwtSecret } from './config/jwt';
import { gatewaySecurityMiddleware } from './middleware/security';

dotenv.config();

export { gatewaySecurityMiddleware };

const app = express();
const PORT: number = Number(process.env.GATEWAY_PORT) || 3001;
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

app.use(helmet());
app.use(cors());

setupMetrics(app, { serviceName: 'gateway', serviceVersion: '1.0.0' });

app.use(metricsMiddleware);

// Security Middleware: Strip untrusted client headers & inject trusted identity only after validation
app.use(gatewaySecurityMiddleware);

const services = {
  auth: process.env.AUTH_SERVICE_URL || 'http://localhost:3002',
};

function createSecureProxy(target: string, pathRewrite: Record<string, string>) {
  return createProxyMiddleware({
    target,
    changeOrigin: true,
    pathRewrite,
    onProxyReq: (proxyReq, req: any) => {
      // Defense-in-depth: Remove any client headers from outgoing proxy request
      proxyReq.removeHeader('x-user-id');
      proxyReq.removeHeader('x-user-role');
      proxyReq.removeHeader('x-user-email');

      // Inject verified identity ONLY if authentication succeeded
      if (req.user && req.user.id) {
        proxyReq.setHeader('x-user-id', req.user.id);
        proxyReq.setHeader('x-user-role', req.user.role || 'customer');
        if (req.user.email) {
          proxyReq.setHeader('x-user-email', req.user.email);
        }
      }
    }
  });
}

app.use('/api/auth', createSecureProxy(services.auth, { '^/api/auth': '' }));

app.use((req, res) => {
  res.status(404).json({ error: 'Service not found' });
});

app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

if (require.main === module) {
  try {
    // Fail-fast configuration validation: abort startup before listening if invalid
    getValidatedJwtSecret();
    app.listen(PORT, "0.0.0.0", () => {
      console.log(`API Gateway running on port ${PORT}`);
      console.log(`Proxying to services:`, services);
    });
  } catch (error) {
    console.error('Failed to start API Gateway:', error);
    process.exit(1);
  }
}

export default app;
