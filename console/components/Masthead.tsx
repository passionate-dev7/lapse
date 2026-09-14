import Link from "next/link";

import { titleCase } from "@/lib/format";

/**
 * Whose portfolio this is, on every screen. A deadline console that does not name the business
 * it is counting for is one browser tab away from being read against the wrong permits.
 */
export function Masthead({ contractor }: { contractor: string }) {
  return (
    <header className="border-b border-rule">
      <div className="mx-auto flex min-h-[68px] w-full max-w-[1080px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-6 py-4">
        <Link href="/" className="flex items-baseline gap-3">
          <span
            className="text-[21px] leading-none"
            style={{ fontVariationSettings: '"opsz" 24', letterSpacing: "-0.01em" }}
          >
            Lapse
          </span>
          <span className="label hidden sm:inline">DOB deadline desk</span>
        </Link>
        <span className="micro" style={{ color: "var(--ink-2)" }}>
          {titleCase(contractor)}
        </span>
      </div>
    </header>
  );
}
