# Boutique Frontend Application

This directory contains the user interface for the online boutique store.

---

## 1. Overview

The frontend is a single-page application (SPA) built with React 19, TypeScript, Vite, and Material-UI. It displays the store catalog, provides a shopping cart, and handles user login and checkout flows.

- **Framework**: React 19 with Vite for fast local building and testing.
- **UI Components**: Material-UI (MUI) for responsive layout and styling.
- **Backend Communication**: Sends requests to the API Gateway at `/api`.
- **Image Assets**: Product images are served statically from `/product-images/`.

---

## 2. Configuration

The application uses Vite environment variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VITE_VERSION` | `production` | Displays the current release version in the header banner. |
| `VITE_API_URL` | `/api` | Base path for all API Gateway requests. |

In Kubernetes, the frontend container runs behind an Nginx reverse proxy that routes `/api` calls directly to the internal API Gateway service.

---

## 3. Container Hardening

The production container uses a multi-stage Docker build:

1. **Build Stage**: Uses `node:24-alpine` to compile TypeScript and build production assets with `npm run build`.
2. **Runtime Stage**: Copies the built `/app/dist` files into a minimal unprivileged container image.
3. **Security Invariant**: Runs under dedicated non-root user `appuser` (UID 10001) with `readOnlyRootFilesystem: true`.

---

## 4. Local Development

Run the following commands to work on the frontend locally:

```bash
# Install dependencies
npm ci

# Start local development server on http://localhost:3000
npm run dev

# Run unit tests
npm test

# Build production bundle
npm run build
```

---

## 5. Related Documentation

- [System Architecture](../../proof/architecture/system-architecture.md): High-level platform topology.
- [Storefront UI Screenshot](../../proof/architecture/01-storefront-ui-demo.png): Visual proof of the running boutique catalog.
