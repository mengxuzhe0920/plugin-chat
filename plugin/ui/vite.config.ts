import { viteConfig } from "@halo-dev/ui-plugin-bundler-kit/vite";

export default viteConfig({
  vite: {
    build: {
      outDir: "../src/main/resources/console",
      emptyOutDir: true,
    },
  },
});
