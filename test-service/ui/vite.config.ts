import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { readFileSync } from "fs";
import { resolve } from "path";

function getApiPort(): number {
  try {
    return parseInt(readFileSync(resolve(__dirname, "..", ".api-port"), "utf8").trim());
  } catch {
    console.warn("No .api-port file found, defaulting to 3001. Start server.py first.");
    return 3001;
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    strictPort: false, // Vite auto-increments if port is taken
    proxy: {
      "/api": `http://127.0.0.1:${getApiPort()}`,
    },
  },
});
