import Link from "next/link";

import { klassTone, type ItemKind, type Klass } from "@/lib/cases";
import { plural, titleCase } from "@/lib/format";
import { SearchBox, SortSelect } from "@/components/FilterControls";
import {
  isFiltered,
  KINDS,
  KLASSES,
  STATES,
  STATE_WORD,
  toggle,
  toQuery,
  withPatch,
  type Filter,
} from "@/lib/view";

/**
 * The slice, spelled out. Every control writes to the query string and reads back from it, so
 * the queue a person is looking at has an address, and the sentence underneath says in words
 * what the address means rather than leaving it to be inferred from which chips look pressed.
 */
export function FilterBar({
  filter,
  shown,
  total,
  sites,
}: {
  filter: Filter;
  shown: number;
  total: number;
  sites: string[];
}) {
  const on = isFiltered(filter);

  return (
    <section className="mt-14 border-t border-rule pt-6">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
        <SearchBox filter={filter} />
        <SortSelect filter={filter} />
      </div>

      <div className="mt-5 flex flex-col gap-3">
        <Row label="Deadline">
          {KLASSES.map((k) => (
            <Chip
              key={k}
              href={toQuery(withPatch(filter, { klass: toggle(filter.klass, k) }))}
              on={filter.klass.includes(k)}
              tone={klassTone(k)}
            >
              {k}
            </Chip>
          ))}
        </Row>
        <Row label="State">
          {STATES.map((s) => (
            <Chip
              key={s}
              href={toQuery(withPatch(filter, { state: toggle(filter.state, s) }))}
              on={filter.state.includes(s)}
            >
              {STATE_WORD[s]}
            </Chip>
          ))}
          {KINDS.map((k: ItemKind) => (
            <Chip
              key={k}
              href={toQuery(withPatch(filter, { kind: toggle(filter.kind, k) }))}
              on={filter.kind.includes(k)}
            >
              {k === "permit" ? "permits" : "violations"}
            </Chip>
          ))}
        </Row>
        {sites.length ? (
          <Row label="Site">
            {sites.map((s) => (
              <Chip
                key={s}
                href={toQuery(withPatch(filter, { site: filter.site === s ? "" : s }))}
                on={filter.site === s}
              >
                {titleCase(s)}
              </Chip>
            ))}
          </Row>
        ) : null}
      </div>

      <p className="micro mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span style={{ color: "var(--ink-2)" }}>{sentence(filter, shown, total)}</span>
        {on ? (
          <Link className="cite" href={toQuery({ ...filter, ...CLEARED })}>
            show all {total}
          </Link>
        ) : null}
      </p>
    </section>
  );
}

const CLEARED = { klass: [], state: [], kind: [], site: "", q: "" } as const;

function sentence(filter: Filter, shown: number, total: number): string {
  if (!isFiltered(filter)) return `All ${plural(total, "open decision")}, ${orderWord(filter)}.`;
  const parts: string[] = [];
  if (filter.klass.length) parts.push(filter.klass.join(" or "));
  if (filter.state.length) parts.push(filter.state.map((s) => STATE_WORD[s]).join(" or "));
  if (filter.kind.length) parts.push(filter.kind.join(" or "));
  if (filter.site) parts.push(`at ${titleCase(filter.site)}`);
  if (filter.q) parts.push(`matching "${filter.q}"`);
  return `${plural(shown, "case")} of ${total}: ${parts.join(", ")}, ${orderWord(filter)}.`;
}

function orderWord(filter: Filter): string {
  if (filter.sort === "latest") return "newest writing first";
  if (filter.sort === "site") return "grouped by address";
  return "most overdue first";
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
      <span className="label w-[68px] shrink-0">{label}</span>
      {children}
    </div>
  );
}

function Chip({
  href,
  on,
  tone,
  children,
}: {
  href: string;
  on: boolean;
  tone?: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className="chip" data-on={on ? "true" : undefined} aria-pressed={on}>
      {tone ? (
        <span
          aria-hidden
          className="inline-block h-[7px] w-[7px] rounded-[1px]"
          style={{ background: tone }}
        />
      ) : null}
      {children}
    </Link>
  );
}
