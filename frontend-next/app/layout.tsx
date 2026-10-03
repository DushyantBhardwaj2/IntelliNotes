import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IntelliNotes — Agentic RAG Assistant",
  description: "Chat over your notes with agentic RAG, web fallback, and execution trace inspection.",
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
