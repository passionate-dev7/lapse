import { plural, squash, titleCase } from "./format";

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
  question_shape?: QuestionShape;
  choices?: Choice[];
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
  answer?: Answer | null;
  timeline: TimelineEntry[];
  delivery: Delivery | null;
  created_at: string;
  updated_at: string;
}

export interface Run {
  contractor: string;
  case_id: string;
  record_type: "run" | "approval";
  status: "run_summary" | "approval_summary";
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

  /** How many of the screened items the engine flagged, split by the verdict it reached. */
  engine_file?: number;
  engine_decide?: number;
  /** How many flagged items this pass actually took to the agent. A sweep takes all of them. */
  considered?: number;
  asked?: number;
  agent_held?: number;
  /** The four deadline classes as the engine counted them across the whole screened corpus. */
  classes?: Partial<Record<Klass, number>>;
}

export const RUN_PREFIX = "run#";

export type RecordKind = "case" | "run" | "other";

/**
 * Which of the three kinds of row this is. `record_type` wins whenever it is present, and the
 * `run#` sort key is only consulted when it is absent.
 *
 * This matters more than it looks. An approval summary is written under a `run#` sort key but
 * carries `record_type: "approval"`, so a test of "run, or the key starts with run#" counts it
 * as a screening pass, and the newest pass on the page becomes the one item the contractor just
 * approved instead of the sweep over their whole portfolio. Anything that is neither a case nor
 * a run is dropped here rather than falling through into the case list, where it would inflate
 * the count in the provenance line.
 */
export function recordKind(raw: { case_id?: string; record_type?: string }): RecordKind {
  const type = raw.record_type;
  if (type === "run") return "run";
  if (type === "case") return "case";
  if (type) return "other";
  return (raw.case_id ?? "").startsWith(RUN_PREFIX) ? "run" : "case";
}

/**
 * The newest pass, by the field that means "when this pass ended" rather than by the sort key
 * that happens to embed it. Compared with `<`, not `localeCompare`: collation is locale aware
 * and these keys are dense in `#`, `-`, `:` and `+`, which collation is entitled to weigh
 * differently from their code points. It agrees with byte order on the keys in the table today,
 * which is exactly what makes it the wrong comparator to leave in place.
 */
function runKey(run: Run): string {
  return run.finished_at || run.case_id.slice(RUN_PREFIX.length) || run.case_id;
}

export function latestRun(runs: Run[]): Run | null {
  let latest: Run | null = null;
  for (const run of runs) {
    if (!latest || runKey(run) > runKey(latest)) latest = run;
  }
  return latest;
}

/**
 * Whether a pass covered the portfolio or was aimed at one case.
 *
 * Approving writes a run record too, because a filing pass is a pass. It screens the same corpus
 * and opens one case, so quoting the newest record makes the headline say a sweep opened one
 * case. The agent now stamps those `record_type: "approval"`, and that is the first test here.
 *
 * The second test is defensive and covers the records already in the table from before that
 * stamp existed. A pass narrowed to a single item still screens everything but takes exactly one
 * flagged item to the agent, so `considered` falls far below the count the engine flagged. A
 * sweep takes all of them. Passes that ran with no agent turn at all carry no `considered` and
 * are sweeps: they read the whole corpus and opened nothing, which is a true thing to report.
 */
export function isSweep(run: Run): boolean {
  if (run.record_type === "approval" || run.status === "approval_summary") return false;
  if (run.considered === undefined || run.considered === null) return true;
  const flagged = (run.engine_file ?? 0) + (run.engine_decide ?? 0);
  return run.considered >= flagged;
}

export function latestSweep(runs: Run[]): Run | null {
  return latestRun(runs.filter(isSweep));
}

export function byNewest(runs: Run[]): Run[] {
  return [...runs].sort((a, b) => (runKey(a) > runKey(b) ? -1 : runKey(a) < runKey(b) ? 1 : 0));
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

/**
 * The serif line on a card names the place, because a contractor recognises a site before they
 * recognise a job number and long before they recognise a permit type code.
 *
 * It used to be `verdict.action` for a FILE case. That is the rulebook's sentence for a class
 * of permit, not a sentence about this permit, so thirteen cards on the live queue carried a
 * byte-identical headline and the only thing separating them was a digit in the mono line
 * underneath. The address is on every record and it is different on almost every one.
 */
export function headline(c: Case): string {
  const address = titleCase(c.item?.address);
  if (address) return address;
  const label = itemLabel(c.item ?? {});
  return label || c.case_id;
}

/**
 * The decision itself, under the place. For DECIDE this is the model's question, which is
 * already written about this specific item. For FILE there is no per item sentence that is not
 * either the rulebook's generic text or the whole draft, so the card says nothing here and lets
 * the artifact line and the draft speak.
 */
export function decisionText(c: Case): string {
  if (c.status !== "needs_decision") return "";
  return squash(c.question ?? c.verdict?.missing?.[0] ?? "") || "One fact is missing.";
}

export interface Answer {
  /** "yes", "no", or an ISO date when the question asked for one. */
  value?: string;
  answers_evidence_id?: string;
  at?: string;
  by?: string;
}

export type QuestionShape = "yes_no" | "date" | "open";

export interface Choice {
  value: string;
  label: string;
}

/**
 * What kind of answer the question takes, and what the choices are called.
 *
 * `verdict.question_shape` and `verdict.choices` are authoritative and are used whenever they
 * are present. They are not present on every row yet: the engine started writing them after
 * these 39 cases were opened, and a case only gains them when a pass rewrites it. Reading only
 * the record would therefore take the answer control off every card currently in the queue, so
 * until the table has turned over, a question with no shape on it is classified from its own
 * text instead.
 *
 * The fallback fails safe. It recognises the lapsed permit question and generic yes or no
 * openers, and anything else gets `open`, which renders no control at all rather than the wrong
 * one. Delete `shapeFromText` and the `choices` default once every row carries the fields.
 */
export function answerShape(c: Case): QuestionShape {
  const declared = c.verdict?.question_shape;
  if (declared === "yes_no" || declared === "date") return declared;
  // Anything else, including a record written before the engine started stamping the shape,
  // degrades to no control rather than to a guessed one.
  return "open";
}

/**
 * The city's framing of each answer, in the order the rulebook puts them, read straight off the
 * record. `choices` is empty for every shape except `yes_no`, so a card cannot render a control
 * for a question that has no set of answers.
 *
 * The generic pair below is a floor, not a guess: it only applies if a record says `yes_no` and
 * then carries no labels, which the contract does not allow. Yes and No are true for any
 * question that is genuinely yes or no, so the floor cannot state something false.
 */
export function answerChoices(c: Case): Choice[] {
  const declared = c.verdict?.choices;
  if (declared?.length) return declared;
  if (answerShape(c) !== "yes_no") return [];
  return [
    { value: "no", label: "No" },
    { value: "yes", label: "Yes" },
  ];
}

/** The answer already on the record, so a card never asks twice without showing the first. */
export function recordedAnswer(c: Case): Answer | null {
  const answer = (c as Case & { answer?: Answer }).answer;
  return answer?.value ? answer : null;
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
    : " That pass opened no new case.";
  return `The last pass read ${corpus} filed under ${contractor} against ${run.source}.${held}${opened}`;
}

/** The count of things the reader never had to see. This is the whole argument of the product. */
export function heldSentence(run: Run | null): string {
  if (!run || !run.items_screened) return "";
  const share = Math.round((run.held / run.items_screened) * 100);
  return `${plural(run.held, "item")} of ${run.items_screened.toLocaleString("en-US")}, ${share} percent, were held without a word.`;
}
