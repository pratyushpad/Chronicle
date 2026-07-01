// Minimal, dependency-light MV3 bundler. Bundles the three entry points with
// esbuild and copies the static manifest + popup assets into dist/.
import { build } from "esbuild";
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const dist = resolve(root, "dist");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

const common = {
  bundle: true,
  format: "iife",
  target: "chrome110",
  logLevel: "info",
  minify: false,
};

await Promise.all([
  build({ ...common, entryPoints: [resolve(root, "src/content/index.ts")], outfile: resolve(dist, "content.js") }),
  build({ ...common, entryPoints: [resolve(root, "src/background.ts")], outfile: resolve(dist, "background.js") }),
  build({ ...common, entryPoints: [resolve(root, "src/popup/popup.ts")], outfile: resolve(dist, "popup.js") }),
]);

cpSync(resolve(root, "manifest.json"), resolve(dist, "manifest.json"));
cpSync(resolve(root, "src/popup/index.html"), resolve(dist, "popup.html"));
cpSync(resolve(root, "src/popup/popup.css"), resolve(dist, "popup.css"));

console.log("✓ Built extension → dist/  (load this folder as an unpacked extension)");
