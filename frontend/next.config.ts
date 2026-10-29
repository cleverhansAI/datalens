import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  reactStrictMode: true,
  experimental: {
    devtoolSegmentExplorer: false
  }
};

export default nextConfig;
