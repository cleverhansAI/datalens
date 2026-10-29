import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DataLens",
  description: "Dataset exploration and curation"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
