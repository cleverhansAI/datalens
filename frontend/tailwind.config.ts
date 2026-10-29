import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          500: "#10B981",
          400: "#34D399"
        }
      }
    }
  },
  plugins: []
};

export default config;
