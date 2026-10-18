import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:5001",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/robot": {
        target: "http://localhost:5002",
        rewrite: (path) => path.replace(/^\/robot/, ""),
      },
    },
  },
});
