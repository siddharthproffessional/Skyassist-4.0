import type { Metadata, Viewport } from "next";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/500.css";
import "./globals.css";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "SkyAssist 4.0 — Airport Digital Twin",
  description: "3D airport digital twin with agentic operations, human approval and full audit. Synthetic demo data.",
};

export const viewport: Viewport = { themeColor: "#060a12", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
