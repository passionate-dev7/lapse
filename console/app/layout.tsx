import type { Metadata } from "next";
import { Barlow, Barlow_Condensed, IBM_Plex_Mono } from "next/font/google";

import { Masthead } from "@/components/Masthead";
import { CONTRACTOR } from "@/lib/store";

import "./globals.css";

const barlow = Barlow({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-barlow",
});

const barlowCondensed = Barlow_Condensed({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
  variable: "--font-barlow-cond",
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
    <html
      lang="en"
      className={`${barlow.variable} ${barlowCondensed.variable} ${plexMono.variable}`}
    >
      <body>
        <Masthead contractor={CONTRACTOR} />
        <main className="drawing mx-auto w-full max-w-[1120px] px-5 pb-24 sm:px-8">
          {children}
        </main>
      </body>
    </html>
  );
}
