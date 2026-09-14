import type { Check } from "@/lib/cases";

/**
 * The audit trail for one verdict. The detail string is never paraphrased: it is what the
 * engine produced, including the dates it compared, so a reader can disagree with the reasoning
 * and not only with the conclusion. A failed check keeps its row rather than being hidden,
 * because the ones that failed are why the case landed in the queue at all.
 */
export function ChecksTable({ checks }: { checks: Check[] }) {
  if (!checks.length) {
    return (
      <p className="data mt-3" style={{ color: "var(--ink-2)" }}>
        This case carries no checks, so no verdict was computed for it.
      </p>
    );
  }

  return (
    <ul className="mt-3 border-t border-rule">
      {checks.map((check, index) => (
        <li
          key={`${check.name}-${index}`}
          className="border-b border-rule py-2.5"
          style={
            check.passed
              ? undefined
              : {
                  // The rule hangs into the gutter so the failed row's columns stay on the
                  // same grid as the passed ones. A row that also shifts sideways reads as a
                  // layout bug rather than as the one thing that did not hold.
                  borderLeft: "2px solid var(--alarm)",
                  marginLeft: "-16px",
                  paddingLeft: "14px",
                  background: "var(--alarm-wash)",
                }
          }
        >
          <div className="grid grid-cols-1 gap-x-4 gap-y-0.5 sm:grid-cols-[44px_168px_1fr] sm:items-baseline">
            <span
              className="label"
              style={{ color: check.passed ? "var(--seal)" : "var(--alarm)" }}
            >
              {check.passed ? "pass" : "fail"}
            </span>
            <span className="data" style={{ color: "var(--ink)" }}>
              {check.name.replace(/_/g, " ")}
            </span>
            <span className="data" style={{ color: "var(--ink-2)" }}>
              {check.detail}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
