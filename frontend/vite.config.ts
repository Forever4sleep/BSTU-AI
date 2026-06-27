import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget =
    env.DEV_PROXY_TARGET || env.VITE_DEV_PROXY_TARGET || "http://localhost:8001";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": { target: proxyTarget, changeOrigin: true },
        "/v1": { target: proxyTarget, changeOrigin: true },
        "/docs": { target: proxyTarget, changeOrigin: true },
        "/openapi.json": { target: proxyTarget, changeOrigin: true },
        "/redoc": { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
