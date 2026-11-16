# syntax=docker/dockerfile:1

# ---- Build stage: compile the TypeScript app into static files -------------------------------
# Debian (slim), not Alpine: the lockfile holds the glibc builds of Vite's native dependencies.
FROM node:26-slim AS builder

WORKDIR /app
# Dependencies change less often than code: copying the manifests first keeps this layer cached.
COPY package.json package-lock.json ./
RUN npm ci
# The API types are generated and committed, so the build needs neither Python nor the API.
COPY . .
RUN npm run build

# ---- Runtime stage: nginx serving the static files and forwarding /api to the API -------------
# The unprivileged variant runs nginx as a non-root user, listening on port 8080.
FROM nginxinc/nginx-unprivileged:1.30-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["wget", "--quiet", "--spider", "http://127.0.0.1:8080/"]
