import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const nextConfig: NextConfig = {
  output: 'standalone',
  images: {
    unoptimized: true,
  },
  // /api/v1/* is proxied by app/api/v1/[...path]/route.ts rather than a rewrite here, because
  // rewrites() is serialized into routes-manifest.json at build time and so cannot honor a
  // runtime BACKEND_URL in the prebuilt image.
};

export default createNextIntlPlugin()(nextConfig);
