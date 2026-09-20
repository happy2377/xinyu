import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  /* config options here */
  devIndicators: false,  // 关闭构建指示器
  reactCompiler: true,
  // 统一走同源 /api，便于本机、局域网与手机公网预览（由 Next 反向代理到 FastAPI）
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
    ];
  },
};

export default nextConfig;
