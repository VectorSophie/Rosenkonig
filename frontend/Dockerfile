# Stage 1: Build the Svelte app
FROM node:20-slim AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy frontend source
COPY frontend/ ./frontend/
COPY package.json ./

# Build the app
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/frontend/build /usr/share/nginx/html

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
