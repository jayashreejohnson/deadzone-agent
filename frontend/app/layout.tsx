import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DeadZone Agent",
  description: "Autonomous offline-pack agent for connectivity dead zones.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
