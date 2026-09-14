import Link from "next/link";

import { itemLabel, klassTone, type Case, type Klass } from "@/lib/cases";
import { daysPhrase, plural, titleCase } from "@/lib/format";
import {
  boroughOf,
  NO_KLASS,
  toQuery,
  withPatch,
  type Filter,
  type KlassFilter,
  type Overview as Shape,
  type SiteBucket,
} from "@/lib/view";

/**
 * The head of the register. A queue of 56 rows has a shape, and until the shape is on the page a
 * person can only find it by scrolling. Every figure here is counted off the rows below it, so
 * the band and the ledger cannot disagree with the list they sit above.
 *
 * Each row is a link that narrows the list, which is why the counts are not decoration: reading
 * "33 lapsed" and pressing it are the same gesture.
 */
/**
 * A deadline class is an engine word. A contractor reads a date, so the band is
 * labelled with what the class means in days, not with what the engine calls it.
 */
const HUMAN: Record<string, string> = {
  lapsed: "already late",
  critical: "due this week",
  due: "due this month",
};

function humanLabel(klass: Klass | null): string {
  return klass ? (HUMAN[klass] ?? klass) : "no clock on these";
}

export function Overview({ shape, filter }: { shape: Shape; filter: Filter }) {
  if (!shape.total) return null;

  const segments: { klass: Klass | null; count: number; label: string }[] = [
    ...shape.byClass.map((b) => ({ klass: b.klass, count: b.count, label: b.klass ?? "" })),
    ...(shape.unclassed
      ? [{ klass: null, count: shape.unclassed, label: "no class on the record" }]
      : []),
  ];

  return (
    <section className="mt-11">
      <h2 className="label">What is due, and when</h2>

      {/* Drawn to scale, ticked at every join: the queue measured, not a bar
          chart of it. Each segment is also the control that filters to it. */}
      <div className="dim mt-5 w-full">
        {segments.map((s) => (
          <Link
            key={s.label}
            href={hrefFor(filter, s.klass)}
            aria-label={`${plural(s.count, "case")}, ${humanLabel(s.klass)}`}
            title={`${plural(s.count, "case")}, ${humanLabel(s.klass)}`}
            className="dim-seg"
            style={{
              flexGrow: s.count,
              flexBasis: 0,
              background: s.klass ? klassTone(s.klass) : "var(--rule-strong)",
            }}
          />
        ))}
      </div>

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1">
        {segments.map((s) => (
          <li key={`legend-${s.label}`} className="micro flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-[7px] w-[7px] rounded-[1px]"
              style={{ background: s.klass ? klassTone(s.klass) : "var(--rule-strong)" }}
            />
            {s.count} {humanLabel(s.klass)}
          </li>
        ))}
      </ul>

      <div className="mt-8 grid grid-cols-1 gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <ul>
          {shape.byClass.map((b) => (
            <Ledger
              key={b.klass ?? "none"}
              tone={klassTone(b.klass)}
              word={b.klass ?? "no class"}
              count={b.count}
              href={hrefFor(filter, b.klass)}
              worst={b.worst}
            />
          ))}
          {shape.unclassed ? (
            <Ledger
              tone="var(--rule-strong)"
              word="no class"
              count={shape.unclassed}
              href={hrefFor(filter, null)}
              worst={null}
              note="The engine could not date these, so they carry no clock and sort last."
            />
          ) : null}
        </ul>

        <div>
          <h3 className="label">Where it lands</h3>
          <ul className="mt-4">
            {shape.boroughs.map((b) => (
              <Borough key={b.site} bucket={b} total={shape.total} filter={filter} />
            ))}
          </ul>
          {shape.crowded.length ? (
            <p className="micro mt-5 max-w-[34ch]" style={{ color: "var(--ink-2)" }}>
              {`${plural(shape.crowded.length, "address", "addresses")} ${shape.crowded.length === 1 ? "carries" : "carry"} more than one open case. ${titleCase(shape.crowded[0].site)} carries ${shape.crowded[0].count}.`}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/**
 * Pressing a class replaces the class filter rather than adding to it, because the band reads as
 * a set of five mutually exclusive slices and a person pressing the second one means "show me
 * that instead". Pressing the one already on clears it and gives the whole queue back.
 */
function hrefFor(filter: Filter, klass: Klass | null): string {
  const value: KlassFilter = klass ?? NO_KLASS;
  const already = filter.klass.length === 1 && filter.klass[0] === value;
  return toQuery(withPatch(filter, { klass: already ? [] : [value] }));
}

function Ledger({
  tone,
  word,
  count,
  href,
  worst,
  note,
}: {
  tone: string;
  word: string;
  count: number;
  href: string;
  worst: Case | null;
  note?: string;
}) {
  const address = worst ? titleCase(worst.item?.address) : "";
  const identifiers = worst ? itemLabel(worst.item ?? {}) : "";

  return (
    <li>
      <Link href={href} className="qty-row">
        <span className="qty-count" style={{ color: tone }}>
          {count}
        </span>
        <span>
          <span className="label" style={{ color: tone }}>
            {word}
          </span>
          {worst ? (
            <span className="micro mt-1.5 block" style={{ color: "var(--ink-2)" }}>
              {`worst: ${daysPhrase(worst.verdict?.days_remaining)}`}
              {address ? `, ${address}` : ""}
              {identifiers ? ` (${identifiers})` : ""}
            </span>
          ) : null}
          {note ? (
            <span className="micro mt-1.5 block" style={{ color: "var(--ink-2)" }}>
              {note}
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

function Borough({
  bucket,
  total,
  filter,
}: {
  bucket: SiteBucket;
  total: number;
  filter: Filter;
}) {
  const on = filter.site.toLowerCase() === bucket.site.toLowerCase();
  const href = toQuery(withPatch(filter, { site: on ? "" : bucket.site }));

  return (
    <li className="border-t border-rule first:border-t-0">
      <Link
        href={href}
        className="block py-3 transition-colors duration-150 hover:bg-sheet-2"
        style={{ marginInline: "-10px", paddingInline: "10px" }}
        aria-current={on ? "true" : undefined}
      >
        <span className="flex items-baseline justify-between gap-4">
          <span className="data" style={{ color: on ? "var(--seal)" : "var(--ink)" }}>
            {bucket.site}
          </span>
          <span className="data" style={{ color: "var(--ink-2)" }}>
            {bucket.count}
          </span>
        </span>
        <span className="mt-2 flex h-[5px] gap-px" style={{ width: `${(bucket.count / total) * 100}%` }}>
          {(["lapsed", "critical", "due", "clear"] as Klass[])
            .filter((k) => bucket.classes[k])
            .map((k) => (
              <span
                key={k}
                className="block"
                style={{ flexGrow: bucket.classes[k], flexBasis: 0, background: klassTone(k) }}
              />
            ))}
        </span>
      </Link>
    </li>
  );
}

/** One sentence naming the single worst thing on the list, because a count never names it. */
export function WorstLine({ worst }: { worst: Case | null }) {
  if (!worst) return null;
  const v = worst.verdict;
  const address = titleCase(worst.item?.address);
  const identifiers = itemLabel(worst.item ?? {});
  const borough = boroughOf(worst.item?.address);
  const where = address || borough || worst.case_id;

  return (
    <p className="prose-16 mt-5 max-w-[66ch]" style={{ color: "var(--ink)" }}>
      <span style={{ color: klassTone(v?.klass) }}>{daysPhrase(v?.days_remaining)}</span>
      {" is the worst of them: "}
      {identifiers ? `${identifiers} at ` : ""}
      {where}
      {". "}
      {worst.status === "awaiting_approval"
        ? "A response is drafted and waiting on you."
        : "Lapse needs one fact from you before it can draft anything for it."}
    </p>
  );
}
