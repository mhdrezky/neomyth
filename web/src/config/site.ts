export const siteConfig = {
  name: "Neomyth",
  title: "Neomyth — Modular AI Toolkit",
  description:
    "Neomyth is a modular AI toolkit with real-time voice, document parsing, and specification tools.",
  url: import.meta.env.PUBLIC_SITE_URL ?? "http://localhost:4321",
  ogImage: "/og.png",
};

export const apiBaseUrl =
  import.meta.env.PUBLIC_API_BASE_URL ?? "http://localhost:5000";
