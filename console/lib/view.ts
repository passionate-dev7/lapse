import {
  itemLabel,
  needsPerson,
  type Case,
  type ItemKind,
  type Klass,
} from "./cases";
import { squash, titleCase } from "./format";

/**
 * The queue is a list of 56 rows on a Monday. What turns that into a tool is the ability to say
 * "only the lapsed ones in Brooklyn" and have the answer be in the address bar, so the next
 * person to open the link sees the same 9 rows. Every selector here reads from a field the agent
 * wrote. Nothing is derived from a category this file invented.
 */

export type Sort = "deadline" | "latest" | "site";
export const SORTS: Sort[] = ["deadline", "latest", "site"];

export const SORT_WORD: Record<Sort, string> = {
  deadline: "most overdue first",
  latest: "most recently written first",
  site: "grouped by address",
};

/** The two statuses a decision can be in. `state` is the URL word for `Case.status`. */
export type State = "draft" | "decide";
export const STATES: State[] = ["draft", "decide"];

export const STATE_WORD: Record<State, string> = {
  draft: "draft ready",
  decide: "your call",
};

export const KLASSES: Klass[] = ["lapsed", "critical", "due", "clear"];
export const KINDS: ItemKind[] = ["permit", "violation"];

/**
 * A row the engine could not date carries no class at all, and nine of them are open right now.
 * "none" is a real slice of the queue rather than an absence to be hidden, so it is a value the
 * URL can carry like any other.
 */
export const NO_KLASS = "none";
export type KlassFilter = Klass | typeof NO_KLASS;
export const KLASS_FILTERS: KlassFilter[] = [...KLASSES, NO_KLASS];

export interface Filter {
  klass: KlassFilter[];
  state: State[];
  kind: ItemKind[];
  site: string;
  q: string;
  sort: Sort;
}

export const EMPTY_FILTER: Filter = {
  klass: [],
  state: [],
  kind: [],
  site: "",
  q: "",
  sort: "deadline",
};

export type RawParams = Record<string, string | string[] | undefined>;

function list<T extends string>(raw: string | string[] | undefined, allowed: readonly T[]): T[] {
  const flat = (Array.isArray(raw) ? raw : [raw ?? ""]).join(",");
  const wanted = flat
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  return allowed.filter((a) => wanted.includes(a));
}

function one(raw: string | string[] | undefined): string {
  return squash(Array.isArray(raw) ? raw[0] : raw);
}

export function parseFilter(params: RawParams): Filter {
  const sortRaw = one(params.sort).toLowerCase() as Sort;
  return {
    klass: list(params.klass, KLASS_FILTERS),
    state: list(params.state, STATES),
    kind: list(params.kind, KINDS),
    site: one(params.site),
    q: one(params.q),
    sort: SORTS.includes(sortRaw) ? sortRaw : "deadline",
  };
}

export function isFiltered(f: Filter): boolean {
  return Boolean(f.klass.length || f.state.length || f.kind.length || f.site || f.q);
}

export function toQuery(f: Filter): string {
  const p = new URLSearchParams();
  if (f.klass.length) p.set("klass", f.klass.join(","));
  if (f.state.length) p.set("state", f.state.join(","));
  if (f.kind.length) p.set("kind", f.kind.join(","));
  if (f.site) p.set("site", f.site);
  if (f.q) p.set("q", f.q);
  if (f.sort !== "deadline") p.set("sort", f.sort);
  const q = p.toString();
  return q ? `/?${q}` : "/";
}

export function withPatch(f: Filter, patch: Partial<Filter>): Filter {
  return { ...f, ...patch };
}

/** Adding or removing one value from a multi-select, which is what clicking a chip means. */
export function toggle<T extends string>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

/**
 * The borough, off the end of the address DOB published. It is the last comma-separated piece of
 * every address in this table, so it is read rather than looked up: a row whose address does not
 * carry one is grouped under the address itself and never under a guess.
 */
export function boroughOf(address: string | null | undefined): string {
  const clean = squash(address);
  if (!clean) return "";
  const parts = clean.split(",");
  return parts.length > 1 ? titleCase(parts[parts.length - 1]) : "";
}

export function siteOf(c: Case): string {
  return titleCase(c.item?.address) || "";
}

function stateOf(c: Case): State | null {
  if (c.status === "awaiting_approval") return "draft";
  if (c.status === "needs_decision") return "decide";
  return null;
}

/** Everything on the row a person might type into the box, joined once per case. */
function haystack(c: Case): string {
  const v = c.verdict;
  return [
    c.case_id,
    c.item?.address,
    c.item?.bin,
    c.item?.item_id,
    itemLabel(c.item ?? {}),
    c.item?.type_label,
    c.item?.description,
    c.item?.permit_type,
    c.item?.filing_status,
    c.job?.description,
    c.job?.status_text,
    v?.klass,
    v?.action,
    v?.artifact,
    v?.anchor_name,
    c.question,
    ...(v?.missing ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function applyFilter(cases: Case[], f: Filter): Case[] {
  const needle = f.q.toLowerCase();
  const site = f.site.toLowerCase();
  const filtered = cases.filter((c) => {
    if (f.klass.length) {
      const klass = c.verdict?.klass;
      if (!f.klass.includes((klass ?? NO_KLASS) as KlassFilter)) return false;
    }
    const state = stateOf(c);
    if (f.state.length && (!state || !f.state.includes(state))) return false;
    if (f.kind.length && !f.kind.includes((c.item?.kind ?? c.kind) as ItemKind)) return false;
    if (site) {
      const address = siteOf(c).toLowerCase();
      const borough = boroughOf(c.item?.address).toLowerCase();
      if (address !== site && borough !== site) return false;
    }
    if (needle && !haystack(c).includes(needle)) return false;
    return true;
  });
  return sortCases(filtered, f.sort);
}

function clock(c: Case): number | null {
  const days = c.verdict?.days_remaining;
  return days === null || days === undefined ? null : days;
}

export function sortCases(cases: Case[], sort: Sort): Case[] {
  const rows = [...cases];
  if (sort === "latest") {
    return rows.sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
  }
  if (sort === "site") {
    return rows.sort((a, b) => {
      const bySite = siteOf(a).localeCompare(siteOf(b));
      if (bySite !== 0) return bySite;
      return byClock(a, b);
    });
  }
  return rows.sort(byClock);
}

/** A case with no clock sorts last: the engine could not date it, so there is nothing to be late
 *  for yet, and putting it above a permit that lapsed three years ago would be a lie of order. */
function byClock(a: Case, b: Case): number {
  const left = clock(a);
  const right = clock(b);
  if (left === null) return right === null ? a.case_id.localeCompare(b.case_id) : 1;
  if (right === null) return -1;
  if (left !== right) return left - right;
  return a.case_id.localeCompare(b.case_id);
}

export interface ClassBucket {
  klass: Klass | null;
  count: number;
  worst: Case | null;
}

export interface SiteBucket {
  site: string;
  count: number;
  classes: Partial<Record<Klass, number>>;
}

export interface Overview {
  total: number;
  byClass: ClassBucket[];
  unclassed: number;
  boroughs: SiteBucket[];
  crowded: SiteBucket[];
  worst: Case | null;
  approvable: number;
}

/**
 * The shape of the problem, counted off the rows on the page and nothing else. It answers the
 * only two questions a contractor has before they start reading: what is going to hurt first,
 * and where is it.
 */
export function overview(cases: Case[]): Overview {
  const pending = cases.filter(needsPerson);

  const byClass: ClassBucket[] = KLASSES.map((klass) => {
    const rows = sortCases(
      pending.filter((c) => c.verdict?.klass === klass),
      "deadline",
    );
    return { klass, count: rows.length, worst: rows[0] ?? null };
  }).filter((b) => b.count > 0);

  const unclassed = pending.filter((c) => !c.verdict?.klass).length;

  const boroughs = bucket(pending, (c) => boroughOf(c.item?.address));
  const crowded = bucket(pending, siteOf).filter((b) => b.count > 1);

  return {
    total: pending.length,
    byClass,
    unclassed,
    boroughs,
    crowded,
    worst: sortCases(pending, "deadline")[0] ?? null,
    approvable: pending.filter((c) => c.status === "awaiting_approval").length,
  };
}

function bucket(cases: Case[], key: (c: Case) => string): SiteBucket[] {
  const map = new Map<string, SiteBucket>();
  for (const c of cases) {
    const site = key(c);
    if (!site) continue;
    const entry = map.get(site) ?? { site, count: 0, classes: {} };
    entry.count += 1;
    const klass = c.verdict?.klass;
    if (klass) entry.classes[klass] = (entry.classes[klass] ?? 0) + 1;
    map.set(site, entry);
  }
  return [...map.values()].sort((a, b) => b.count - a.count || a.site.localeCompare(b.site));
}
