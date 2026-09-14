import Link from "next/link";

import { klassTone, type Case, type ItemKind, type Klass } from "@/lib/cases";
import { plural, titleCase } from "@/lib/format";
import { SearchBox, SortSelect } from "@/components/FilterControls";
import {
  boroughOf,
  isFiltered,
  KINDS,
  KLASS_FILTERS,
  NO_KLASS,
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
  pending,
  shown,
  sites,
}: {
  filter: Filter;
  pending: Case[];
  shown: number;
  sites: string[];
}) {
  const total = pending.length;
  const on = isFiltered(filter);
  const n = counts(pending);

  return (
    <section className="mt-14 border-t border-rule pt-6">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
        <SearchBox filter={filter} />
        <SortSelect filter={filter} />
      </div>

      <div className="mt-5 flex flex-col gap-3">
        <Row label="Deadline">
          {KLASS_FILTERS.map((k) =>
            n.klass[k] ? (
              <Chip
                key={k}
                href={toQuery(withPatch(filter, { klass: toggle(filter.klass, k) }))}
                on={filter.klass.includes(k)}
                tone={k === NO_KLASS ? "var(--rule-strong)" : klassTone(k as Klass)}
                count={n.klass[k]}
              >
                {k === NO_KLASS ? "no class" : k}
              </Chip>
            ) : null,
          )}
        </Row>
        <Row label="State">
          {STATES.map((s) =>
            n.state[s] ? (
              <Chip
                key={s}
                href={toQuery(withPatch(filter, { state: toggle(filter.state, s) }))}
                on={filter.state.includes(s)}
                count={n.state[s]}
              >
                {STATE_WORD[s]}
              </Chip>
            ) : null,
          )}
          {KINDS.map((k: ItemKind) =>
            n.kind[k] ? (
              <Chip
                key={k}
                href={toQuery(withPatch(filter, { kind: toggle(filter.kind, k) }))}
                on={filter.kind.includes(k)}
                count={n.kind[k]}
              >
                {k === "permit" ? "permits" : "violations"}
              </Chip>
            ) : null,
          )}
        </Row>
        {sites.length ? (
          <Row label="Borough">
            {sites.map((s) => (
              <Chip
                key={s}
                href={toQuery(withPatch(filter, { site: filter.site === s ? "" : s }))}
                on={filter.site === s}
                count={n.site[s]}
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

const CLEARED: Partial<Filter> = { klass: [], state: [], kind: [], site: "", q: "" };

/**
 * Nothing matched. It says what was asked for and how many rows it was asked of, because a page
 * that only says "nothing here" is indistinguishable from a page whose read failed, and on a
 * deadline product those two mean opposite things.
 */
export function NoMatches({ filter, total }: { filter: Filter; total: number }) {
  return (
    <section className="mt-12 border-t border-rule pt-10">
      <h2 className="record-title max-w-[42ch]">
        {`No open decision matches that, out of the ${plural(total, "on the queue", "on the queue")}.`}
      </h2>
      <p className="prose-16 mt-4 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
        {`This is a filter finding nothing, not a clear portfolio. The queue behind it still holds ${plural(total, "open decision")}. Take one of the filters off, or clear them all.`}
      </p>
      <p className="mt-6">
        <Link className="btn btn-secondary" href={toQuery({ ...filter, ...CLEARED })}>
          Show all {total}
        </Link>
      </p>
    </section>
  );
}

function sentence(filter: Filter, shown: number, total: number): string {
  if (!isFiltered(filter)) return `All ${plural(total, "open decision")}, ${orderWord(filter)}.`;
  const parts: string[] = [];
  if (filter.klass.length) {
    parts.push(filter.klass.map((k) => (k === NO_KLASS ? "carrying no class" : k)).join(" or "));
  }
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
  count,
  children,
}: {
  href: string;
  on: boolean;
  tone?: string;
  count?: number;
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
      {count === undefined ? null : (
        <span style={{ opacity: 0.62, fontVariantNumeric: "tabular-nums" }}>{count}</span>
      )}
    </Link>
  );
}

/**
 * How many open decisions each facet would hold on its own. Counted over the whole queue rather
 * than over the current slice, so a chip never reads zero because of a filter it is not part of,
 * and a facet nothing falls into is left off the row rather than offered as a dead control.
 */
function counts(pending: Case[]) {
  const klass: Record<string, number> = {};
  const state: Record<string, number> = {};
  const kind: Record<string, number> = {};
  const site: Record<string, number> = {};
  for (const c of pending) {
    const k = c.verdict?.klass ?? NO_KLASS;
    klass[k] = (klass[k] ?? 0) + 1;
    if (c.status === "awaiting_approval") state.draft = (state.draft ?? 0) + 1;
    if (c.status === "needs_decision") state.decide = (state.decide ?? 0) + 1;
    const kd = c.item?.kind ?? c.kind;
    if (kd) kind[kd] = (kind[kd] ?? 0) + 1;
    const b = boroughOf(c.item?.address);
    if (b) site[b] = (site[b] ?? 0) + 1;
  }
  return { klass, state, kind, site };
}
