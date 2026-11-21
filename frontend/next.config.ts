import type { NextConfig } from "next";

// Production build = static export served by the SkyAssist FastAPI server (api/server.py) on the same origin.
// Development = `next dev` with /web proxied to the Python API on :8600.
const isProd = process.env.NODE_ENV === "production";
const API = process.env.SKYASSIST_API ?? "http://127.0.0.1:8600";

const nextConfig: NextConfig = {
  ...(isProd ? { output: "export" as const } : {}),
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: { "*.css": { loaders: ["@tailwindcss/turbopack"], as: "*.css" } },
  },
  ...(isProd ? {} : { async rewrites() { return [{ source: "/web/:path*", destination: `${API}/web/:path*` }]; } }),
};

export default nextConfig;
