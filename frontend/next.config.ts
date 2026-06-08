import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy all /api/* calls to the FastAPI backend during development.
  // In production, the backend URL is set via NEXT_PUBLIC_API_URL.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },

  // Allow images from localhost (for future avatar/document previews)
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },

  // Strict mode for catching React issues early
  reactStrictMode: true,
};

export default nextConfig;
