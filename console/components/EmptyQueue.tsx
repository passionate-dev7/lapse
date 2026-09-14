import { ClosedList } from "@/components/ClosedList";
import { heldSentence, runSentence, type Case, type Run } from "@/lib/cases";
import { ago, longDate, stampUTC, titleCase } from "@/lib/format";

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

      <ClosedList cases={cases} heading="Closed without you" />
    </section>
  );
}
