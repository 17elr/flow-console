import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Flow Console - AI 电商自动化",
  description: "商品图片、参数审核与店铺草稿工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="h-full">
      <body className="min-h-full antialiased">{children}</body>
    </html>
  );
}
