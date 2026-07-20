import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 开发模式：把 /api/* 转发到 FastAPI (http://127.0.0.1:8000)
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
  // 生产构建：不启用 standalone（保持默认，便于部署）
  output: undefined,
};

export default nextConfig;
