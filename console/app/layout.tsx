import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader } from "next/font/google";

import { Masthead } from "@/components/Masthead";
import { CONTRACTOR } from "@/lib/store";

import "./globals.css";

const newsreader = Newsreader({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-newsreader",
  axes: ["opsz"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: {
    default: "Lapse: DOB deadline queue",
    template: "%s",
  },
  description:
    "Lapse watches a contractor's DOB permits and violations on a schedule, works out what is about to lapse, drafts the renewal or the correction, and interrupts once per item. This console only holds the decisions that are genuinely a person's.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${newsreader.variable} ${plexMono.variable}`}>
      <body>
        <Masthead contractor={CONTRACTOR} />
        <main className="mx-auto w-full max-w-[1080px] px-6 pb-24">{children}</main>
      </body>
    </html>
  );
}
