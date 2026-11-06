# Build stage
FROM node:24-alpine AS builder
WORKDIR /app

ARG VITE_VERSION=dev
ENV VITE_VERSION=$VITE_VERSION

ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production runtime stage
FROM node:24-alpine
RUN apk upgrade --no-cache

# Create dedicated non-root user and group (UID/GID 10001)
RUN addgroup -g 10001 -S appgroup && \
    adduser -u 10001 -S appuser -G appgroup

WORKDIR /app

# Copy production static assets from builder with non-root ownership
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist

# Install pinned serve and apply compression patch (CVE-2026-87776 remediation)
RUN npm install -g serve@14.2.6 destroy@1.2.0
COPY compression-1.8.2.tgz /tmp/
RUN tar -xzf /tmp/compression-1.8.2.tgz -C /usr/local/lib/node_modules/serve/node_modules/compression --strip-components=1 && \
    rm -rf /tmp/compression-1.8.2.tgz /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

USER 10001:10001

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000", "--single"]
