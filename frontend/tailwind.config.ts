import type {Config} from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        muted: "#667085",
        paper: "#f8fafc",
        line: "#d9e2ec",
        brand: "#2563eb",
        skysoft: "#eaf4ff",
        mintsoft: "#e9fbf4",
        ambersoft: "#fff7df"
      },
      boxShadow: {
        card: "0 8px 24px rgb(37 99 235 / 0.06)"
      }
    }
  },
  plugins: []
};

export default config;
