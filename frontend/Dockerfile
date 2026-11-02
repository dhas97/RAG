# ---------------------------------------------------------------------------
# Frontend Dockerfile — two-stage build: compile React → serve with Nginx.
#
# WHY TWO STAGES?
#   Stage 1 (builder) installs Node.js, all npm packages, and runs the Vite
#   build. This produces a /app/dist folder of static HTML/CSS/JS files.
#   Stage 2 copies only that dist folder into a tiny Nginx image, discarding
#   Node, npm, and all build tools. The final image is much smaller and has
#   a smaller attack surface than an image that ships Node at runtime.
# ---------------------------------------------------------------------------

# ── Stage 1: build the React app ──────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first so Docker caches the npm install layer.
# The expensive npm install step is only re-run when package*.json changes.
COPY package*.json ./
RUN npm install

# Copy source code after dependencies so source changes don't bust the
# cached npm install layer.
COPY . .

# VITE_API_URL tells the compiled JS where the backend lives.
# Passed in from docker-compose.yml (build.args). An empty string means
# "same origin" — requests go to the same host/port serving the frontend,
# and Nginx proxies /api/* to the backend container.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

# Compile TypeScript/JSX and bundle everything into /app/dist.
RUN npm run build

# ── Stage 2: serve the compiled static files with Nginx ───────────────────
FROM nginx:alpine

# Copy only the compiled output — no Node, no source code, no build tools.
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace Nginx's default config with ours (see nginx.conf for details).
# Our config proxies /api/* to the backend and handles React's client-side
# routing by falling back to index.html for unknown paths.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
# "daemon off" keeps Nginx in the foreground so Docker can track the process.
CMD ["nginx", "-g", "daemon off;"]
