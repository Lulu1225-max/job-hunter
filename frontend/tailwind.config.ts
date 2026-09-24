import type {Config} from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "hsl(var(--text-primary) / <alpha-value>)",
        muted: "hsl(var(--text-secondary) / <alpha-value>)",
        paper: "hsl(var(--background) / <alpha-value>)",
        white: "hsl(var(--surface) / <alpha-value>)",
        "surface-muted": "hsl(var(--surface-muted) / <alpha-value>)",
        line: "hsl(var(--border) / <alpha-value>)",
        brand: "hsl(var(--primary) / <alpha-value>)",
        "brand-hover": "hsl(var(--primary-hover) / <alpha-value>)",
        "brand-active": "hsl(var(--primary-active) / <alpha-value>)",
        skysoft: "hsl(var(--primary-soft) / <alpha-value>)",
        mintsoft: "hsl(var(--success-soft) / <alpha-value>)",
        ambersoft: "hsl(var(--warning-soft) / <alpha-value>)"
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)"
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        card: "var(--shadow-sm)",
        md: "var(--shadow-md)"
      }
    }
  },
  plugins: []
};

export default config;
