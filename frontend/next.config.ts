import path from 'path';
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  reactStrictMode: false,  // Disable Strict Mode for dev (optional)
};

export default nextConfig;
