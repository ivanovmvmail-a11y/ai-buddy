import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Самодостаточная сборка для Docker (frontend/Dockerfile). На Vercel не мешает.
  output: "standalone",
};

export default nextConfig;
