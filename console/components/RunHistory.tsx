import Link from "next/link";

import { byNewest, isSweep, klassTone, type Klass, type Run } from "@/lib/cases";
import { ago, plural, stampUTC } from "@/lib/format";

/**
 * What ran while nobody was watching. The product's claim is that it works a portfolio on a
 * schedule and interrupts once per item, and until the passes are on a page that claim is
 * invisible: the queue only shows what survived screening, never the screening.
 *
 * Every figure is read off a run record. Nothing is counted from the rows that happen to be
 * left in the table, because that measures the leftovers and understates every pass that held
 * something, which is most of them.
 */
export function RunHistory({
  runs,
  limit,
  heading,
}: {
  runs: Run[];
  limit?: number;
  heading: string;
}) {
  const ordered = byNewest(runs);
  const shown = limit ? ordered.slice(0, limit) : ordered;

  if (!shown.length) {
    return (
      <section className="mt-16 border-t border-rule pt-6">
        <h2 className="label">{heading}</h2>
        <p className="prose-16 mt-4 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
          No pass has written a summary under this contractor yet. Until one does, this page can
          only say that nobody has looked, which is not the same as saying nothing is due.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-16 border-t border-rule pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 className="label">{heading}</h2>
        {limit && ordered.length > shown.length ? (
          <Link className="cite micro" href="/runs">
            all {ordered.length} passes on record
          </Link>
        ) : null}
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <thead>
            <tr className="border-b border-rule-strong">
              <Th>Finished</Th>
              <Th>Pass</Th>
              <Th right>Screened</Th>
              <Th right>Held</Th>
              <Th right>Opened</Th>
              <Th right>Drafted</Th>
              <Th right>Asked</Th>
              <Th right>Filed</Th>
              <Th right>Vetoed</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((run) => (
              <tr key={run.case_id} className="border-b border-rule align-top">
                <Td>
                  <span className="data block" style={{ color: "var(--ink)" }}>
                    {stampUTC(run.finished_at)}
                  </span>
                  <span className="micro block">{ago(run.finished_at)}</span>
                </Td>
                <Td>
                  <span className="data block" style={{ color: "var(--ink)" }}>
                    {isSweep(run) ? "portfolio sweep" : "single case filing"}
                  </span>
                  <span className="micro block">
                    {run.permits_screened || run.violations_screened
                      ? `${run.permits_screened} permits, ${run.violations_screened} violations`
                      : run.source}
                  </span>
                </Td>
                <Num value={run.items_screened} />
                <Num value={run.held} />
                <Num value={run.cases_opened} />
                <Num value={run.drafted} />
                <Num value={run.needs_decision} />
                <Num value={run.filed} />
                <Num value={run.vetoed} tone={run.vetoed ? "var(--alarm)" : undefined} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Ramp run={shown[0]} />
    </section>
  );
}

/** The class split the newest pass measured across everything it read, not just what it opened. */
function Ramp({ run }: { run: Run }) {
  const classes = run.classes;
  if (!classes) return null;
  const order: Klass[] = ["lapsed", "critical", "due", "clear"];
  const present = order.filter((k) => classes[k]);
  if (!present.length) return null;
  const total = present.reduce((n, k) => n + (classes[k] ?? 0), 0);

  return (
    <p className="micro mt-6 flex flex-wrap items-center gap-x-5 gap-y-2">
      <span style={{ color: "var(--ink-2)" }}>
        {`That pass classed ${plural(total, "dated item")} across the whole portfolio:`}
      </span>
      {present.map((k) => (
        <span key={k} className="inline-flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-[8px] w-[8px] rounded-[1px]"
            style={{ background: klassTone(k) }}
          />
          <span style={{ color: "var(--ink)" }}>{`${classes[k]} ${k}`}</span>
        </span>
      ))}
    </p>
  );
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th scope="col" className={`label pb-2.5 pr-5 font-normal ${right ? "text-right" : ""}`}>
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return <td className="py-3.5 pr-5">{children}</td>;
}

function Num({ value, tone }: { value: number | undefined; tone?: string }) {
  return (
    <td className="py-3.5 pr-5 text-right">
      <span className="data" style={{ color: tone ?? (value ? "var(--ink)" : "var(--ink-3)") }}>
        {value ?? 0}
      </span>
    </td>
  );
}

/**
 * The cadence, quoted from the deployment rather than inferred from the rows above. A page that
 * read "every day" off nine passes that all ran this afternoon would be describing a wish. This
 * says what the schedule is configured to be and says who configured it, and the table above is
 * the separate question of what has actually fired.
 */
export function Cadence({ schedule }: { schedule: string | null }) {
  if (!schedule) return null;
  return (
    <p className="micro mt-5 max-w-[80ch]" style={{ color: "var(--ink-2)" }}>
      {`Configured cadence: ${schedule}. That is the EventBridge schedule the deploy script writes, read out of this deployment's configuration. What it has actually done is the table, not this line.`}
    </p>
  );
}
