# Boutique Store Frontend

Modern React application powered by [Vite](https://vite.dev), [Material-UI](https://mui.com), and [Vitest](https://vitest.dev).

## Development

```bash
# Deterministic dependency installation
npm ci

# Start Vite development server on http://localhost:3000
npm run dev
# or
npm start
```

## Testing & Quality Gates

```bash
# Execute unit & smoke tests via Vitest
npm test

# Run dependency vulnerability audit (zero High/Critical findings tolerated)
npm audit --audit-level=high

# Run TypeScript typecheck & production bundle
npm run build
```

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `VITE_VERSION` | `dev` | Deployment version displayed in top banner |
| `VITE_API_URL` | `/api` | Base URL for backend microservices API gateway |

## Container Build & Security

The Docker container runs as a dedicated non-root user (`appuser`, UID 10001) serving static files from `/app/dist` over port 3000:

```bash
docker build -t boutique-frontend:latest .
docker run --rm -p 3000:3000 boutique-frontend:latest
```
