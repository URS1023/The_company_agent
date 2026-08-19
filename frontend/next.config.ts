import type { NextConfig } from "next";

const apiOrigin = process.env.COMPANY_AGENT_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
      { source: "/health/:path*", destination: `${apiOrigin}/health/:path*` }
    ];
  }
};

export default nextConfig;
