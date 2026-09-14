import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import { DynamoDBClient, QueryCommand, UpdateItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall, unmarshall } from "@aws-sdk/util-dynamodb";

import { recordKind, type Case, type Run, type TimelineEntry } from "./cases";


export const TABLE = process.env.LAPSE_TABLE ?? "lapse-cases";
export const CONTRACTOR = process.env.LAPSE_CONTRACTOR ?? "VARSITY PLBG AND HTG INC";
export const REGION = process.env.LAPSE_AWS_REGION ?? "us-east-1";

export type Origin = "dynamodb" | "preview";

/**
 * A state the console can be in that is neither a queue nor a finished night shift. Each one
 * names what is actually wrong, because "Nothing needs you" over a table that does not exist
 * would be the most expensive sentence this product could print.
 */
export interface Problem {
  headline: string;
  detail: string;
}

export interface Read {
  cases: Case[];
  runs: Run[];
  origin: Origin;
  problem: Problem | null;
}

/**
 * Vercel reserves every AWS_ prefixed name for its own runtime, and that runtime's role has no
 * access to this table, so the console carries its own key under a LAPSE_ prefix.
 */
function credentials(): { accessKeyId: string; secretAccessKey: string } | undefined {
  const accessKeyId = process.env.LAPSE_AWS_ACCESS_KEY_ID?.trim();
  const secretAccessKey = process.env.LAPSE_AWS_SECRET_ACCESS_KEY?.trim();
  return accessKeyId && secretAccessKey ? { accessKeyId, secretAccessKey } : undefined;
}

function hasCredentials(): boolean {
  return Boolean(credentials() || process.env.AWS_PROFILE);
}

let client: DynamoDBClient | null = null;

function db(): DynamoDBClient {
  if (!client) client = new DynamoDBClient({ region: REGION, credentials: credentials() });
  return client;
}

/**
 * Cases, run summaries and everything else share the partition key. They are told apart here
 * and nowhere else, so no screen can render an approval summary as a case or as a pass.
 *
 * An approval summary is kept and filed with the passes rather than dropped. It is a pass: it
 * ran the agent, it screened the corpus, and it filed something, and the run history is the one
 * page whose whole job is to show what ran. `isSweep` is what keeps it out of the headline,
 * where quoting it would report a portfolio sweep that opened a single case. Dropping the row
 * here instead would mean an approval the contractor made themselves could never appear in the
 * record of what this agent has done.
 */
function split(rows: Record<string, unknown>[]): { cases: Case[]; runs: Run[] } {
  const cases: Case[] = [];
  const runs: Run[] = [];
  for (const row of rows) {
    if (row.record_type === "approval") {
      runs.push(row as unknown as Run);
      continue;
    }
    const kind = recordKind(row as { case_id?: string; record_type?: string });
    if (kind === "other") continue;
    if (kind === "run") {
      runs.push(row as unknown as Run);
    } else {
      const c = row as unknown as Case;
      cases.push({
        ...c,
        item: c.item ?? {},
        job: c.job ?? null,
        timeline: c.timeline ?? [],
        // Spread first, then default. Listing the fields instead silently drops every field the
        // engine adds later: `question_shape` and `choices` were both lost that way, which took
        // the answer control off all 39 open questions while the records themselves carried it.
        verdict: {
          ...c.verdict,
          outcome: c.verdict?.outcome ?? "DECIDE",
          klass: c.verdict?.klass ?? null,
          due_on: c.verdict?.due_on ?? null,
          days_remaining: c.verdict?.days_remaining ?? null,
          anchor_name: c.verdict?.anchor_name ?? "",
          checks: c.verdict?.checks ?? [],
          missing: c.verdict?.missing ?? [],
          action: c.verdict?.action ?? "",
          artifact: c.verdict?.artifact ?? "",
          citation: c.verdict?.citation ?? "",
          evidence_id: c.verdict?.evidence_id ?? "",
        },
      });
    }
  }
  return { cases, runs };
}

/**
 * A developer copy of the table, used only when LAPSE_PREVIEW is set and only to exercise the
 * dense rendering path against rows that exist somewhere. It cannot reach production: `.local`
 * is in .vercelignore, so the file is not in the deployment, and the variable is not set there.
 * When it is in use the provenance line at the foot of the page says so in those words.
 */
async function preview(): Promise<Read | null> {
  if (process.env.LAPSE_PREVIEW !== "1") return null;
  let raw: string;
  try {
    raw = await readFile(path.join(process.cwd(), ".local", "preview.json"), "utf8");
  } catch {
    return null;
  }
  const parsed = JSON.parse(raw) as { Items?: Record<string, unknown>[] };
  const rows = (parsed.Items ?? []).filter((r) => r.contractor === CONTRACTOR);
  return { ...split(rows), origin: "preview", problem: null };
}

export async function listCases(): Promise<Read> {
  const local = await preview();
  if (local) return local;

  if (!hasCredentials()) {
    return {
      cases: [],
      runs: [],
      origin: "dynamodb",
      problem: {
        headline: "This deployment has no key for the case table.",
        detail: `LAPSE_AWS_ACCESS_KEY_ID and LAPSE_AWS_SECRET_ACCESS_KEY are not set, so nothing was read from ${TABLE} in ${REGION}. An empty queue here would mean nothing was asked, not that nothing is due.`,
      },
    };
  }

  try {
    const out = await db().send(
      new QueryCommand({
        TableName: TABLE,
        KeyConditionExpression: "contractor = :c",
        ExpressionAttributeValues: marshall({ ":c": CONTRACTOR }),
      }),
    );
    const rows = (out.Items ?? []).map((item) => unmarshall(item));
    return { ...split(rows), origin: "dynamodb", problem: null };
  } catch (error) {
    const err = error as { name?: string; message?: string };
    if (err.name === "ResourceNotFoundException") {
      return {
        cases: [],
        runs: [],
        origin: "dynamodb",
        problem: {
          headline: "The case table has not been created yet.",
          detail: `DynamoDB in ${REGION} has no table called ${TABLE}. Lapse writes one row per decision it makes, so until the first screening pass runs there is nothing here to be right or wrong about. This page is not saying you are clear.`,
        },
      };
    }
    return {
      cases: [],
      runs: [],
      origin: "dynamodb",
      problem: {
        headline: "The case table refused the read.",
        detail: `DynamoDB answered ${err.name ?? "an error"} for table ${TABLE} in ${REGION}: ${err.message ?? "no message"}. Nothing below was read, so treat this page as blank rather than as clear.`,
      },
    };
  }
}

/**
 * One case, read back from the table. The approve route uses this rather than trusting the
 * browser for the DOB item id, because that id is what the filing function restricts its pass
 * to, and a client that could name it could aim the agent at somebody else's permit.
 */
export async function getCase(caseId: string): Promise<Case | null> {
  const { cases } = await listCases();
  return cases.find((c) => c.case_id === caseId) ?? null;
}

/**
 * The cadence as this deployment is configured, or nothing. The console's key reaches DynamoDB
 * and one Lambda, not EventBridge, so the schedule cannot be read from the system that holds it
 * and is carried here as configuration instead. It is printed with that caveat attached rather
 * than dressed up as an observation, and the run table underneath is the observation.
 */
export function schedule(): string | null {
  return process.env.LAPSE_SCHEDULE?.trim() || null;
}

export function filingFunction(): string | null {
  const name = process.env.LAPSE_AGENT_FUNCTION?.trim();
  if (!name || !hasCredentials()) return null;
  return name;
}

/**
 * Approving is two writes and the second one is not the console's. The condition on the status
 * keeps a second tab, or a retried POST, from stacking approvals onto a case that already moved.
 */
export async function recordApproval(caseId: string): Promise<void> {
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const entry: TimelineEntry = {
    at: now,
    event: "approval.granted",
    detail: "The contractor approved the drafted response in the console.",
  };
  await db().send(
    new UpdateItemCommand({
      TableName: TABLE,
      Key: marshall({ contractor: CONTRACTOR, case_id: caseId }),
      UpdateExpression:
        "SET timeline = list_append(if_not_exists(timeline, :empty), :events), updated_at = :now",
      ConditionExpression: "#status = :expected",
      ExpressionAttributeNames: { "#status": "status" },
      ExpressionAttributeValues: marshall({
        ":empty": [] as TimelineEntry[],
        ":events": [entry],
        ":now": now,
        ":expected": "awaiting_approval",
      }),
    }),
  );
}

/**
 * The answer to the one question, written onto the case and nowhere else.
 *
 * The status deliberately does not move. `docs/RECORD.md` has four statuses and none of them
 * means "answered", and inventing a fifth here would put a value in the table that the engine
 * has never agreed to read. What this does is real and complete on its own terms: the decision
 * the product asked for is now on the record, in a timeline event whose name carries the value,
 * so the next pass can act on it. The card says exactly that and claims nothing more.
 */
export async function recordAnswer(
  caseId: string,
  answer: string,
  evidenceId: string,
  question: string,
) {
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const entry: TimelineEntry = {
    at: now,
    event: "answered",
    detail: question
      ? `The contractor answered ${answer} in the console to: ${question}`
      : `The contractor answered ${answer} in the console.`,
  };
  await db().send(
    new UpdateItemCommand({
      TableName: TABLE,
      Key: marshall({ contractor: CONTRACTOR, case_id: caseId }),
      UpdateExpression:
        "SET #answer = :answer, timeline = list_append(if_not_exists(timeline, :empty), :events), updated_at = :now",
      ConditionExpression: "#status = :expected",
      ExpressionAttributeNames: { "#status": "status", "#answer": "answer" },
      ExpressionAttributeValues: marshall({
        ":answer": {
          value: answer,
          // Copied verbatim off the verdict being answered. The engine uses it to tell whether
          // DOB's record moved between the question going out and the answer coming back, and
          // refuses a stale answer rather than acting on it.
          answers_evidence_id: evidenceId,
          at: now,
          by: "the contractor",
        },
        ":empty": [] as TimelineEntry[],
        ":events": [entry],
        ":now": now,
        ":expected": "needs_decision",
      }),
    }),
  );
}


/**
 * Resolving an answered question. Same function and the same server side `only`, with no
 * `approve` key, so the pass re-reads the item with the answer on the record and turns the
 * DECIDE into a FILE with a draft. It never files: approving that draft is still a separate
 * press by a person.
 *
 * This used to destroy the answer. `open_case` rebuilt the case from the feeds and carried over
 * only the fields the feeds cannot regenerate, and `answer` was not on that list, so a pass
 * started this quickly replaced the case body and took the answer with it. Re-enabled only after
 * the carry list was fixed and the race was re-run against the live table: answer written,
 * invoke 1.5 seconds behind it, and the row reached FILE with a draft and the answer still on it.
 */
export async function handOffForResolve(itemId: string): Promise<void> {
  const name = filingFunction();
  if (!name) throw new Error("No agent function is configured on this deployment.");
  const { InvokeCommand, LambdaClient } = await import("@aws-sdk/client-lambda");
  const lambda = new LambdaClient({ region: REGION, credentials: credentials() });
  const out = await lambda.send(
    new InvokeCommand({
      FunctionName: name,
      InvocationType: "Event",
      Payload: Buffer.from(JSON.stringify({ live: true, with_model: true, only: itemId })),
    }),
  );
  if (out.StatusCode !== 202) {
    throw new Error(`Lambda ${name} answered ${out.StatusCode} instead of accepting the pass.`);
  }
}

/**
 * Filing outlives a serverless request, so the invoke is asynchronous. A 202 means the filing
 * function accepted the case. It never means a response reached DOB, and only that function may
 * write `filed` and the message id that proves one did.
 *
 * `only` narrows the pass to the single DOB item behind this case, which is what keeps this one
 * agent turn rather than a full portfolio sweep. `approve` carries the human decision through,
 * so the function files instead of stopping at a draft.
 */
export async function handOffForFiling(caseId: string, itemId: string): Promise<void> {
  const name = filingFunction();
  if (!name) throw new Error("No filing function is configured on this deployment.");
  const { InvokeCommand, LambdaClient } = await import("@aws-sdk/client-lambda");
  const lambda = new LambdaClient({ region: REGION, credentials: credentials() });
  const out = await lambda.send(
    new InvokeCommand({
      FunctionName: name,
      InvocationType: "Event",
      Payload: Buffer.from(
        JSON.stringify({ live: true, with_model: true, only: itemId, approve: [caseId] }),
      ),
    }),
  );
  if (out.StatusCode !== 202) {
    throw new Error(`Lambda ${name} answered ${out.StatusCode} instead of accepting the filing.`);
  }
}
