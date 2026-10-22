FROM node:24-alpine AS base
# Node's CA store is compiled in, and before 24.22.1 it trusts the compromised eMudhra
# intermediates; a stale local node:24-alpine would otherwise build without complaint.
RUN node -e "const [major, minor, patch] = process.versions.node.split('.').map(Number); \
  if (major === 24 && (minor < 22 || (minor === 22 && patch < 1))) { \
    console.error('Node ' + process.version + ' trusts compromised eMudhra CAs: pull node:24-alpine again'); \
    process.exit(1); \
  }"

# Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED 1

RUN npm run build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

# shadow provides usermod/groupmod for PUID/PGID remapping in the entrypoint
RUN apk add --no-cache su-exec shadow

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Set the correct permission for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Automatically leverage output traces to reduce image size
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/messages ./messages

# Entrypoint drops to nextjs (remapped to PUID/PGID when set); when the
# container is started as a non-root uid it execs directly
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

CMD ["node", "server.js"]
