import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Proxy all /api/* calls to the FastAPI backend.
  // In local dev: BACKEND_URL defaults to http://localhost:8000
  // In production (Vercel): Set BACKEND_URL to your Render backend URL
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },

  // Allow images from localhost and production backend
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
      },
      {
        protocol: "https",
        hostname: "*.onrender.com",
      },
    ],
  },

  // Strict mode for catching React issues early
  reactStrictMode: true,

  // Output standalone for optimized production builds
  output: "standalone",
};

export default nextConfig;
