"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * The one action on an awaiting_approval card. It records the approval on the case and hands
 * the case to the filing function. It deliberately never reports that anything reached DOB:
 * only the filing function can write `filed`, because only it holds the message id that proves
 * a response left. When no filing function is configured the button says so on the button.
 */
export function ApproveAction({ caseId, enabled }: { caseId: string; enabled: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function approve() {
    setBusy(true);
    setNote(null);
    setFailed(false);
    try {
      const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "approve" }),
      });
      const body = (await res.json()) as { error?: string; message?: string };
      if (!res.ok) {
        setNote(body.error ?? `The write failed with status ${res.status}.`);
        setFailed(true);
        setBusy(false);
        return;
      }
      setNote(body.message ?? "Approval recorded.");
      setBusy(false);
      router.refresh();
    } catch (error) {
      setNote((error as Error).message);
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <div className="mt-7">
      <button
        type="button"
        className="btn btn-primary"
        disabled={!enabled || busy}
        onClick={approve}
        title={
          enabled
            ? "Records your approval on the case and hands it to the filing function"
            : "LAPSE_AGENT_FUNCTION is not set on this deployment, so pressing this could not file anything"
        }
      >
        {busy ? "Recording" : "Approve and file"}
      </button>
      {note ? (
        <p
          className="data mt-3 max-w-[62ch]"
          style={{ color: failed ? "var(--alarm)" : "var(--ink-2)" }}
        >
          {note}
        </p>
      ) : null}
    </div>
  );
}
