import { NextResponse } from "next/server";

import { RUN_PREFIX } from "@/lib/cases";
import { filingFunction, getCase, handOffForFiling, recordApproval } from "@/lib/store";

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

  const body = (await request.json().catch(() => ({}))) as { action?: string };
  if (body.action !== "approve") {
    return NextResponse.json(
      { error: `This endpoint takes one action, "approve". It was given ${JSON.stringify(body.action ?? null)}.` },
      { status: 400 },
    );
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
