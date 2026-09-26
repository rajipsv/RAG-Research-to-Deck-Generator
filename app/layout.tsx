import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Research-to-Deck Generator",
  description:
    "Turn a research topic into a cited, branded slide deck via RAG over OpenAlex papers.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
