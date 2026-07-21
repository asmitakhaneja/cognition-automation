import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `vite dev` the frontend runs on :5173 and proxies /api to the
// FastAPI backend on :8000. In production the backend serves the built assets.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
