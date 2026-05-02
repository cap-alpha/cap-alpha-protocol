import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
    oxc: {
        // Enables JSX transform for .tsx files (React 17+ automatic runtime)
        jsx: {
            runtime: "automatic",
            importSource: "react",
        },
    },
    test: {
        globals: true,
        environment: "node",
        exclude: [
            "tests/e2e/**",
            "tests/e2e_js/**",
            "node_modules/**",
        ],
    },
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "."),
        },
    },
});
