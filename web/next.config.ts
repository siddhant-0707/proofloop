import type { NextConfig } from "next";

const apiOrigin = process.env.PROOFLOOP_API ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // A Gemma Loop makes about ten model calls and can take a minute; the default is 30 s.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
