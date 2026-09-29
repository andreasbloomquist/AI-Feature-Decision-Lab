import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    // The full recommended set (including the React Compiler rules such as set-state-in-effect),
    // with every rule as an error so CI fails on it.
    rules: Object.fromEntries(Object.keys(reactHooks.configs.recommended.rules).map((rule) => [rule, "error"])),
  },
);
