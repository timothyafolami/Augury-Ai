import { defineConfig } from "vitest/config";

/** Node by default, and a DOM only where a test needs one.
 *
 * Most of what the interface computes is pure and should stay testable
 * without a browser standing in the way. The print path is the exception: it
 * is entirely about where a node sits in the document, so it is tested against
 * a real document via the per-file `@vitest-environment` pragma.
 */
export default defineConfig({
  test: {
    environment: "node",
  },
});
