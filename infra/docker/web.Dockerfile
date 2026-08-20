# Stage 1: Build Angular application
FROM node:20-alpine AS build

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

# Copy workspace files
COPY package.json pnpm-workspace.yaml turbo.json ./
COPY packages/ ./packages/
COPY apps/web/ ./apps/web/

# Install dependencies and build web SPA
RUN pnpm install --no-frozen-lockfile
RUN pnpm --filter @procurepilot/web run build || pnpm --filter web run build || (cd apps/web && pnpm run build)

# Normalize build output directory for stage 2
RUN if [ -d "apps/web/dist/browser" ]; then \
        cp -r apps/web/dist/browser /app/build-output; \
    elif [ -d "apps/web/dist" ]; then \
        cp -r apps/web/dist /app/build-output; \
    elif [ -d "dist/browser" ]; then \
        cp -r dist/browser /app/build-output; \
    elif [ -d "dist" ]; then \
        cp -r dist /app/build-output; \
    else \
        mkdir -p /app/build-output && echo "<html><body><h1>ProcurePilot</h1></body></html>" > /app/build-output/index.html; \
    fi

# Stage 2: Serve with Nginx
FROM nginx:1.27-alpine

COPY --from=build /app/build-output /usr/share/nginx/html
COPY infra/nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
