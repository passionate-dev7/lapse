"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * The answer to the one question. Yes and no are the two values of a single decision, not two
 * actions competing for the card, so they are a matched pair in the same weight and neither is
 * the primary. There is no third button: leaving it alone is already the way to not answer, and
 * a Skip control would be a second action that does nothing.
 *
 * Nothing here sends anything. The card says so, and so does the reply.
 */
export function AnswerAction({ caseId, answered }: { caseId: string; answered: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState<"yes" | "no" | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function answer(value: "yes" | "no") {
    setBusy(value);
    setNote(null);
    setFailed(false);
    try {
      const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "answer", answer: value }),
      });
      const body = (await res.json()) as { error?: string; message?: string };
      if (!res.ok) {
        setNote(body.error ?? `The write failed with status ${res.status}.`);
        setFailed(true);
        setBusy(null);
        return;
      }
      setNote(body.message ?? "Answer recorded.");
      setBusy(null);
      router.refresh();
    } catch (error) {
      setNote((error as Error).message);
      setFailed(true);
      setBusy(null);
    }
  }

  return (
    <div className="mt-7">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null}
          onClick={() => answer("yes")}
          title="Records yes on this case. Nothing is sent."
        >
          {busy === "yes" ? "Recording" : "Yes"}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null}
          onClick={() => answer("no")}
          title="Records no on this case. Nothing is sent."
        >
          {busy === "no" ? "Recording" : "No"}
        </button>
        <span className="micro">
          {answered
            ? `you answered ${answered}, and you can change it`
            : "recorded on the case, then read by the next pass"}
        </span>
      </div>
      <p
        className="data mt-4 max-w-[64ch]"
        style={{ color: failed ? "var(--alarm)" : "var(--ink-2)" }}
      >
        {note ??
          "Answering does not send anything and does not renew anything. It puts the one fact Lapse could not read on the record, so the next pass can work out which filing is the right one."}
      </p>
    </div>
  );
}
