import { daysPhrase, titleCase } from "@/lib/format";
import type { Case, Run } from "@/lib/cases";

/**
 * Five facts above the fold, one line each.
 *
 * What stood here was "The last pass read 140 permits and 95 violations filed
 * under X against live NYC Open Data. It held 179 items that were not yet
 * anybody's problem." That is a sentence about the pipeline, written by someone
 * proud of the pipe and not yet thinking about the person holding the phone at a
 * job site. The pipeline detail is a footnote now and the README carries the rest.
 *
 * A contractor wants four things in the first screen: whose desk this is, whether
 * the data is current, how many decisions are theirs, and which one is already
 * costing money.
 */
export function OperatorStrip({
  pending,
  worst,
  run,
  contractor,
  lapsed,
}: {
  pending: number;
  worst: Case | null;
  run: Run | null;
  contractor: string;
  lapsed: number;
}) {
  const synced = run?.finished_at
    ? run.finished_at.slice(0, 16).replace("T", " ")
    : "the last pass";

  const cost =
    lapsed > 0
      ? `${lapsed} already past their date${
          worst?.verdict?.days_remaining != null
            ? `, the worst by ${daysPhrase(worst.verdict.days_remaining)}`
            : ""
        }`
      : pending > 0
        ? `${pending} still inside their window`
        : "nothing past its date";

  return (
    <section className="strip">
      <div className="strip-row">
        <span className="strip-role">Duty officer</span>
        <span aria-hidden="true" style={{ color: "var(--rule-strong)" }}>
          ·
        </span>
        <span>{titleCase(contractor)}</span>
        <span className="strip-live">
          <span className="strip-dot" aria-hidden="true" />
          LIVE · synced {synced} UTC
        </span>
      </div>

      <p className="strip-contract">
        {pending === 0
          ? "Nothing needs you."
          : `${pending} ${pending === 1 ? "decision is" : "decisions are"} yours.`}
      </p>

      <p className="strip-cost">{cost}</p>

      <p className="strip-machine micro">
        The overnight pass did the reading.
        {run
          ? ` ${run.items_screened} items screened, ${run.held} held without a word.`
          : " Counts come from the cases themselves until a pass writes a summary."}
      </p>
    </section>
  );
}
