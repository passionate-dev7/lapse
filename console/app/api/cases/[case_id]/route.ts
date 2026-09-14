import { NextResponse } from "next/server";

import { decisionText, RUN_PREFIX } from "@/lib/cases";
import {
  filingFunction,
  getCase,
  handOffForFiling,
  recordAnswer,
  recordApproval,
} from "@/lib/store";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ case_id: string }> },
) {
  const { case_id: caseId } = await params;

  if (caseId.startsWith(RUN_PREFIX)) {
    return NextResponse.json(
      { error: "That id belongs to a run summary, not a case. Nothing was written." },
      { status: 400 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as { action?: string; answer?: string };
  if (body.action !== "approve" && body.action !== "answer") {
    return NextResponse.json(
      {
        error: `This endpoint takes two actions, "approve" and "answer". It was given ${JSON.stringify(body.action ?? null)}.`,
      },
      { status: 400 },
    );
  }

  if (body.action === "answer") {
    const given = (body.answer ?? "").trim();
    const isChoice = given === "yes" || given === "no";
    const isDate = /^\d{4}-\d{2}-\d{2}$/.test(given);
    if (!isChoice && !isDate) {
      return NextResponse.json(
        {
          error: `An answer is "yes", "no", or a date as YYYY-MM-DD. It was given ${JSON.stringify(body.answer ?? null)}.`,
        },
        { status: 400 },
      );
    }
    // A date in the past is not a plan, it is a deadline that has already gone. The engine
    // refuses one with a visible failed check; refusing it here as well means the contractor
    // finds out while the picker is still in front of them.
    if (isDate) {
      const parsed = new Date(`${given}T00:00:00Z`);
      const today = new Date().toISOString().slice(0, 10);
      if (Number.isNaN(parsed.getTime()) || given.slice(0, 10) < today) {
        return NextResponse.json(
          {
            error: `${given} is not a date Lapse can track from. Pick today or later, because the date you set becomes the deadline it counts down to.`,
          },
          { status: 400 },
        );
      }
    }
    const target = await getCase(caseId);
    if (!target) {
      return NextResponse.json(
        { error: `No case ${caseId} under this contractor. Nothing was written.` },
        { status: 404 },
      );
    }
    if (target.status !== "needs_decision") {
      return NextResponse.json(
        {
          error: `This case is ${target.status}, not waiting on a decision, so there is no question here to answer. Reload to see where it got to.`,
        },
        { status: 409 },
      );
    }
    const evidenceId = target.verdict?.evidence_id?.trim() ?? "";
    if (!evidenceId) {
      return NextResponse.json(
        {
          error:
            "This case carries no evidence id, so an answer could not be tied to the verdict it answers and nothing was written.",
        },
        { status: 422 },
      );
    }

    try {
      await recordAnswer(caseId, given, evidenceId, decisionText(target));
    } catch (error) {
      const err = error as { name?: string; message?: string };
      if (err.name === "ConditionalCheckFailedException") {
        return NextResponse.json(
          {
            error:
              "This case moved on before the answer landed, so nothing was written. Reload to see where it got to.",
          },
          { status: 409 },
        );
      }
      return NextResponse.json({ error: err.message ?? "The write failed." }, { status: 502 });
    }

    // Deliberately no pass is started here. Kicking one off immediately after the write races
    // it: the pass rewrites the case record without the `answer` map, so the answer is erased
    // and the question is asked again. Proved on case 0ac6feaa03d5cb2b, where two console
    // answers at 13:22:11 and 13:22:27 were followed by two `asked` events at 13:22:31 and
    // 13:22:45 and no `answer` left on the row. Until the pass preserves it, the scheduled run
    // is the only thing that should read an answer, and the copy below says exactly that.
    return NextResponse.json({
      ok: true,
      message: `Answered ${given}, and that is on the case now. The next scheduled pass reads it and writes the draft. Nothing has been sent and this one is not handled yet.`,
    });
  }

  const name = filingFunction();
  if (!name) {
    return NextResponse.json(
      {
        error:
          "LAPSE_AGENT_FUNCTION is not set on this deployment, or it carries no AWS credentials. Nothing was approved, because an approval that cannot be filed is worse than no approval.",
      },
      { status: 503 },
    );
  }

  // The DOB item id is read back off the record rather than taken from the request, because it
  // is what the filing function narrows its pass to. A caller who could name it could aim the
  // agent at a permit that is not theirs.
  const item = await getCase(caseId);
  if (!item) {
    return NextResponse.json(
      { error: `No case ${caseId} under this contractor. Nothing was written.` },
      { status: 404 },
    );
  }
  if (item.status !== "awaiting_approval") {
    return NextResponse.json(
      {
        error: `This case is ${item.status}, not awaiting approval, so there is nothing here to approve. Reload to see where it got to.`,
      },
      { status: 409 },
    );
  }
  const itemId = item.item?.item_id?.trim();
  if (!itemId) {
    return NextResponse.json(
      {
        error:
          "This case carries no DOB item id, so the filing function could not be pointed at a single item and a pass was not started.",
      },
      { status: 422 },
    );
  }

  try {
    await recordApproval(caseId);
  } catch (error) {
    const err = error as { name?: string; message?: string };
    if (err.name === "ConditionalCheckFailedException") {
      return NextResponse.json(
        {
          error:
            "This case is no longer waiting for approval, so nothing was written. Reload to see where it got to.",
        },
        { status: 409 },
      );
    }
    return NextResponse.json({ error: err.message ?? "The write failed." }, { status: 502 });
  }

  try {
    await handOffForFiling(caseId, itemId);
  } catch (error) {
    return NextResponse.json(
      {
        error: `Your approval is recorded on the case, but ${name} would not take the filing: ${(error as Error).message}`,
      },
      { status: 502 },
    );
  }

  return NextResponse.json({
    ok: true,
    message: `Approval recorded and handed to ${name}. This case turns to filed, with a message id on it, only when the response has actually left.`,
  });
}
