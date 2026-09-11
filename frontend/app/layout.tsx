import "./globals.css";
import type {ReactNode} from "react";
import type {Metadata} from "next";

export const metadata: Metadata = {
  title: {default: "Job Hunter", template: "%s | Job Hunter"},
  description: "AI-assisted job search workspace for university students and early-career candidates.",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html>
      <body>{children}</body>
    </html>
  );
}
