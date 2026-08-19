import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "企业 AI 工作台",
  description: "把企业知识、文件和工作能力放进一个可追溯的工作台。"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
