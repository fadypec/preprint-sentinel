// dashboard/tailwind.config.ts
// NOTE: This project uses Tailwind CSS v4, which does not use a config file
// for standard configuration. Dark mode is configured via CSS in app/globals.css
// using: @custom-variant dark (&:is(.dark *))
//
// This file is retained for tooling compatibility. For v4 configuration,
// see app/globals.css and postcss.config.mjs.

const config = {
  darkMode: ["class"] as const,
  content: [
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
