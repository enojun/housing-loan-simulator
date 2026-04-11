# Stage 1: Clone and build the MCP server
FROM node:20-slim AS builder

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone https://github.com/kentaroajisaka/tax-law-mcp.git
WORKDIR /build/tax-law-mcp
RUN npm install && npm run build

# Stage 2: Production image
FROM node:20-slim

WORKDIR /app

# Copy frontend app
COPY package.json ./
RUN npm install --production

COPY server.js ./
COPY public/ ./public/

# Copy built MCP server
COPY --from=builder /build/tax-law-mcp ./tax-law-mcp

EXPOSE 8080
ENV PORT=8080

CMD ["node", "server.js"]
