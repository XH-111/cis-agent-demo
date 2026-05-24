/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f2933",
        line: "#d8dee8",
        panel: "#f7f9fc",
        accent: "#2563eb",
        success: "#16803c",
        warning: "#b45309",
        danger: "#b42318"
      }
    }
  },
  plugins: []
};
