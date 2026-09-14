import Link from "next/link";

import { titleCase } from "@/lib/format";

/**
 * The header strip of the sheet. Whose portfolio this is, on every screen: a
 * deadline console that does not name the business it counts for is one browser
 * tab away from being read against the wrong permits.
 */
export function Masthead({ contractor }: { contractor: string }) {
  return (
    <header className="title-bar">
      <div className="title-bar-inner mx-auto w-full max-w-[1120px] px-5 sm:px-8">
        <Link href="/" className="flex items-baseline gap-4">
          <span className="wordmark">Lapse</span>
          <span className="label hidden sm:inline">DOB deadline sheet</span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="sheet-no">
            <span style={{ color: "var(--flag)" }}>NYC</span> Open Data
          </span>
          <span className="data" style={{ color: "var(--ink)" }}>
            {titleCase(contractor)}
          </span>
        </div>
      </div>
    </header>
  );
}
