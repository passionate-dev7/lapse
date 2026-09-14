import { plural, stampUTC } from "@/lib/format";
import { CONTRACTOR, REGION, TABLE, type Origin } from "@/lib/store";

/**
 * The title block of the sheet. A drawing states who issued it, from what, and
 * when it was read, in a ruled box at the bottom right. Same obligation here: a
 * number with no origin is a rumour with good posture, so every page ends by
 * naming the table, the region, the partition and the moment of the read.
 */
export function Provenance({
  origin,
  cases,
  runs,
}: {
  origin: Origin;
  cases: number;
  runs: number;
}) {
  const from =
    origin === "preview"
      ? `local preview file for ${TABLE}, a developer mode that never runs in production`
      : `${TABLE}, ${REGION}`;

  const rows: [string, string][] = [
    ["Read from", from],
    ["Partition", CONTRACTOR],
    ["Rows", `${plural(cases, "case")}, ${plural(runs, "run record")}`],
    ["Read at", stampUTC(new Date().toISOString())],
  ];

  return (
    <section className="title-block">
      <div className="title-block-head">
        <span className="label" style={{ color: "var(--ink)" }}>
          Lapse deadline sheet
        </span>
        <span className="label">DOB · NYC Open Data</span>
      </div>
      <dl className="title-block-body">
        {rows.map(([key, value]) => (
          <div
            key={key}
            className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-rule py-2 last:border-b-0"
          >
            <dt className="label" style={{ minWidth: "82px" }}>
              {key}
            </dt>
            <dd className="micro" style={{ color: "var(--ink-2)", overflowWrap: "anywhere" }}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
