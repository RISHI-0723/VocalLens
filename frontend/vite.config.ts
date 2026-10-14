import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The frontend talks to the FastAPI backend. In dev, /api is proxied to the
// backend so the browser needs no CORS. In prod, set VITE_API_BASE to the API
// origin (the service layer prepends it).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev proxy: browser calls /api -> FastAPI backend (no CORS needed in dev).
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
