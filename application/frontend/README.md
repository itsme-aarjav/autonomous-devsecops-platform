# Boutique Frontend

The frontend is a **React** shopping interface for the demo application. It shows products, supports the shopping flow, and calls the backend through the API gateway. It uses Vite to build the browser application.

## Run or test locally

From `application/frontend/`:

```bash
npm ci
npm run dev
npm test
npm run build
```

`npm run dev` starts the local development server; it does **not** recreate the deleted AWS demo.

## Configuration and container

- `VITE_API_URL` — API gateway URL; the default is `/api`.
- `VITE_VERSION` — optional version label for the UI.
- The production container serves the built files and uses non-root user ID `10001`.

## Evidence

- [Storefront screenshot](../../proof/architecture/01-storefront-ui-demo.png)
- [Historical storefront API check](../../proof/terminal-outputs/05-storefront-api.txt)
- [Main project overview](../../README.md)
