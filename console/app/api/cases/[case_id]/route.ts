import { NextResponse } from "next/server";

import { RUN_PREFIX } from "@/lib/cases";
import { filingFunction, handOffForFiling, recordApproval } from "@/lib/store";

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
    await handOffForFiling(caseId);
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
