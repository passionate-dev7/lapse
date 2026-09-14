import {
  heldSentence,
  itemLabel,
  runSentence,
  STATUS_WORD,
  type Case,
  type Run,
} from "@/lib/cases";
import { ago, longDate, plural, stampUTC, titleCase } from "@/lib/format";

/**
 * The healthy state, and the point of the product. It is not a blank page with a shrug on it:
 * it is a report of a shift that ran while nobody was watching. Every figure in it is read off
 * a run record, never counted from whatever rows happen to be left in the table.
 */
export function EmptyQueue({
  cases,
  run,
  contractor,
}: {
  cases: Case[];
  run: Run | null;
  contractor: string;
}) {
  const closed = cases
    .filter((c) => c.status === "filed" || c.status === "dismissed")
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 6);

  const neverRan = !run && !cases.length;

  return (
    <section className="report-in pt-20">
      <h1 className="statement max-w-[20ch]">
        {neverRan ? "Lapse has not made a pass yet." : "Nothing is about to lapse."}
      </h1>

      <p className="prose-16 mt-7 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
        {neverRan
          ? `The case table is there and it is empty. No permit or violation under ${titleCase(contractor)} has been screened, so this page is not telling you that you are clear. It is telling you nobody has looked.`
          : runSentence(run, titleCase(contractor))}
      </p>

      {!neverRan && heldSentence(run) ? (
        <p className="data mt-6 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
          {heldSentence(run)}
        </p>
      ) : null}

      {run ? (
        <p className="micro mt-7">
          {`last pass ${ago(run.finished_at)}, ${stampUTC(run.finished_at)}`}
          {run.as_of ? `, reading the city as of ${longDate(run.as_of)}` : ""}
        </p>
      ) : null}

      {closed.length ? (
        <div className="mt-16">
          <h2 className="label">Closed without you</h2>
          <ul className="mt-5 border-t border-rule">
            {closed.map((c) => (
              <li
                key={c.case_id}
                className="grid grid-cols-1 gap-x-6 gap-y-1 border-b border-rule py-4 sm:grid-cols-[150px_1fr_auto] sm:items-baseline"
              >
                <span className="micro">{longDate(c.updated_at?.slice(0, 10))}</span>
                <span className="prose-16">
                  {titleCase(c.item?.address) || itemLabel(c.item ?? {}) || c.case_id}
                  <span className="micro" style={{ marginLeft: "10px" }}>
                    {itemLabel(c.item ?? {})}
                  </span>
                </span>
                <span className="micro" style={{ color: "var(--ink-2)" }}>
                  {c.status === "filed" && c.delivery?.message_id
                    ? `filed, ${c.delivery.message_id}`
                    : STATUS_WORD[c.status]}
                </span>
              </li>
            ))}
          </ul>
          {cases.length > closed.length ? (
            <p className="micro mt-4">
              {plural(cases.length - closed.length, "older case")} not shown.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
