import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests for pure lib code (formatters). Node environment on purpose: these
// functions must behave identically on the server, so they're tested without a DOM.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
