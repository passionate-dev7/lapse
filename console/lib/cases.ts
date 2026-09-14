import { plural, squash } from "./format";

/**
 * The shapes in docs/RECORD.md, and nothing beyond them. Every field on screen is read from a
 * record written by the agent. Where a field can be absent on a real row it is optional here,
 * so a missing value renders as nothing rather than as a confident zero.
 */

export type CaseStatus = "awaiting_approval" | "needs_decision" | "filed" | "dismissed";
export type Outcome = "FILE" | "DECIDE" | "HOLD";
export type Klass = "lapsed" | "critical" | "due" | "clear";
export type ItemKind = "permit" | "violation";

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface TimelineEntry {
  at: string;
  event: string;
  detail: string;
}

/**
 * One `item` block covers both feeds. A permit row carries job and permit_type; a violation row
 * carries number and type_code. Neither carries the other's fields, so both sides are optional
 * and the renderer asks what is there instead of assuming.
 */
export interface Item {
  kind?: ItemKind;
  item_id?: string;
  address?: string;
  bin?: string;
  url?: string;
  source?: string;
  status?: string;

  job?: string;
  job_doc?: string;
  job_type?: string;
  permit_type?: string;
  permit_subtype?: string;
  permit_sequence?: string;
  work_type?: string;
  filing_status?: string;
  issued_on?: string;
  expires_on?: string;
  permittee?: string;
  owner?: string;
  self_cert?: string;
  superseded_by?: string;

  number?: string;
  violation_number?: string;
  ecb_number?: string;
  type_code?: string;
  type_label?: string;
  category?: string;
  description?: string;
  disposition_date?: string | null;
  disposition_comments?: string;
}

export interface Job {
  job?: string;
  doc?: string;
  job_type?: string;
  status?: string;
  status_text?: string;
  description?: string;
  latest_action_on?: string | null;
  signed_off_on?: string | null;
  initial_cost?: string;
  building_type?: string;
  landmarked?: string;
  applicant?: string;
  source?: string;
}

export interface Verdict {
  outcome: Outcome;
  klass: Klass | null;
  due_on: string | null;
  days_remaining: number | null;
  anchor_name: string;
  checks: Check[];
  missing: string[];
  action: string;
  artifact: string;
  citation: string;
  evidence_id: string;
}

export interface Delivery {
  mode?: string;
  to?: string;
  intended?: string;
  message_id?: string;
  reason?: string;
  sent_at?: string;
}

export interface Case {
  contractor: string;
  case_id: string;
  record_type?: "case";
  status: CaseStatus;
  kind: ItemKind;
  item: Item;
  job: Job | null;
  verdict: Verdict;
  draft_text: string | null;
  question: string | null;
  timeline: TimelineEntry[];
  delivery: Delivery | null;
  created_at: string;
  updated_at: string;
}

export interface Run {
  contractor: string;
  case_id: string;
  record_type: "run";
  status: "run_summary";
  finished_at: string;
  permits_screened: number;
  violations_screened: number;
  items_screened: number;
  held: number;
  cases_opened: number;
  drafted: number;
  awaiting_approval: number;
  needs_decision: number;
  filed: number;
  vetoed: number;
  source: string;
  as_of: string;
  timeline?: TimelineEntry[];
  created_at?: string;
  updated_at?: string;
}

export const RUN_PREFIX = "run#";

export function isRun(raw: { case_id?: string; record_type?: string }): boolean {
  return raw.record_type === "run" || (raw.case_id ?? "").startsWith(RUN_PREFIX);
}

/** ISO timestamps sort lexicographically, so the highest `run#` key is the newest pass. */
export function latestRun(runs: Run[]): Run | null {
  if (!runs.length) return null;
  return [...runs].sort((a, b) => a.case_id.localeCompare(b.case_id))[runs.length - 1];
}

/** The two statuses that cost the contractor attention. Everything else is history. */
export function needsPerson(c: Case): boolean {
  return c.status === "awaiting_approval" || c.status === "needs_decision";
}

/**
 * `days_remaining` is already the urgency, because the four classes are cut from it. Sorting on
 * it ascending puts the most overdue lapse at the top and walks down to the furthest away,
 * which is the order a person works the list in. A case with no clock sorts last, since the
 * engine could not date it and there is nothing to be late for yet.
 */
export function queue(cases: Case[]): Case[] {
  return cases.filter(needsPerson).sort((a, b) => {
    const left = a.verdict?.days_remaining;
    const right = b.verdict?.days_remaining;
    if (left === null || left === undefined) return right === null || right === undefined ? 0 : 1;
    if (right === null || right === undefined) return -1;
    if (left !== right) return left - right;
    return a.case_id.localeCompare(b.case_id);
  });
}

/**
 * The four classes read as a ramp from oxblood to grey, because the variable is ordinal. The
 * word is printed next to the colour on every card, so nothing here is carried by hue alone.
 */
export const KLASS_TONE: Record<Klass, string> = {
  lapsed: "var(--lapsed)",
  critical: "var(--critical)",
  due: "var(--due)",
  clear: "var(--clear)",
};

export function klassTone(klass: Klass | null | undefined): string {
  return klass ? KLASS_TONE[klass] : "var(--ink-3)";
}

export const STATUS_WORD: Record<CaseStatus, string> = {
  awaiting_approval: "draft ready",
  needs_decision: "your call",
  filed: "filed",
  dismissed: "closed",
};

/**
 * What the item is, assembled from the identifiers DOB itself prints. Nothing is invented: a
 * field that is blank on the row is left out of the line rather than filled in.
 */
export function itemLabel(item: Item): string {
  const parts: string[] = [];
  if (item.kind === "violation") {
    if (item.type_code) parts.push(`type ${item.type_code}`);
    const number = item.number || item.violation_number || item.item_id;
    if (number) parts.push(`violation ${number}`);
    if (item.ecb_number) parts.push(`ECB ${item.ecb_number}`);
  } else {
    if (item.job) parts.push(`job ${item.job}${item.job_doc ? `/${item.job_doc}` : ""}`);
    if (item.permit_type) parts.push(`permit ${item.permit_type}`);
    if (item.permit_sequence) parts.push(`seq ${item.permit_sequence}`);
    if (!parts.length && item.item_id) parts.push(`permit ${item.item_id}`);
  }
  return parts.join(", ");
}

/** The one sentence at the top of a card: what the engine says to do, or what it needs to know. */
export function headline(c: Case): string {
  if (c.status === "needs_decision") {
    return squash(c.question ?? c.verdict?.missing?.[0] ?? "") || "One fact is missing.";
  }
  return squash(c.verdict?.action ?? "") || "A response is drafted and waiting.";
}

export function passedChecks(v: Verdict): Check[] {
  return (v?.checks ?? []).filter((c) => c.passed);
}

export function failedChecks(v: Verdict): Check[] {
  return (v?.checks ?? []).filter((c) => !c.passed);
}

/**
 * The run record is the only honest source for how much a pass covered. Counting the rows left
 * in the table measures the leftovers, which understates every pass that held something.
 */
export function runSentence(run: Run | null, contractor: string): string {
  if (!run) {
    return `No screening pass has written a summary for ${contractor} yet, so there is no throughput to quote.`;
  }
  const read: string[] = [];
  if (run.permits_screened) read.push(plural(run.permits_screened, "permit"));
  if (run.violations_screened) read.push(plural(run.violations_screened, "violation"));
  const corpus = read.length ? read.join(" and ") : plural(run.items_screened ?? 0, "item");
  const held = run.held
    ? ` It held ${plural(run.held, "item")} that were not yet anybody's problem and said nothing about them.`
    : "";
  const opened = run.cases_opened
    ? ` ${plural(run.cases_opened, "case")} came out of it.`
    : " Nothing came out of it.";
  return `The last pass read ${corpus} filed under ${contractor} against ${run.source}.${held}${opened}`;
}

/** The count of things the reader never had to see. This is the whole argument of the product. */
export function heldSentence(run: Run | null): string {
  if (!run || !run.items_screened) return "";
  const share = Math.round((run.held / run.items_screened) * 100);
  return `${plural(run.held, "item")} of ${run.items_screened.toLocaleString("en-US")}, ${share} percent, were held without a word.`;
}
