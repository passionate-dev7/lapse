"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Answer, Choices } from "@/lib/cases";

/**
 * The answer to the one question. Yes and no are the two values of a single decision, not two
 * actions competing for the card, so they are a matched pair in the same weight and neither is
 * the primary. There is no third button: leaving it alone is already the way to not answer, and
 * a Skip control would be a second action that does nothing.
 *
 * Nothing here sends anything. Answering turns the question into a draft, and that draft still
 * needs a separate press. The copy says so before and after.
 */
export function AnswerAction({
  caseId,
  choices,
  answer,
}: {
  caseId: string;
  choices: Choices;
  answer: Answer | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<"yes" | "no" | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function send(value: "yes" | "no") {
    setBusy(value);
    setNote(null);
    setFailed(false);
    try {
      const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "answer", answer: value }),
      });
      const body = (await res.json()) as { error?: string; message?: string; resolving?: boolean };
      if (!res.ok) {
        setNote(body.error ?? `The write failed with status ${res.status}.`);
        setFailed(true);
        setBusy(null);
        return;
      }
      setNote(body.message ?? "Answer recorded.");
      setBusy(null);
      router.refresh();
      // A pass takes around fifteen seconds, which outlives this request, so the card cannot
      // show the draft on the first refresh. One later refresh is honest about that rather than
      // leaving a person looking at an unchanged card wondering whether the press registered.
      if (body.resolving) setTimeout(() => router.refresh(), 18_000);
    } catch (error) {
      setNote((error as Error).message);
      setFailed(true);
      setBusy(null);
    }
  }

  const given = answer?.value ?? null;

  return (
    <div className="mt-7">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null}
          onClick={() => send("no")}
          style={given === "no" ? { borderColor: "var(--seal)", color: "var(--seal)" } : undefined}
          title="Records this answer on the case. Nothing is sent."
        >
          {busy === "no" ? "Recording" : choices.no}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null}
          onClick={() => send("yes")}
          style={given === "yes" ? { borderColor: "var(--seal)", color: "var(--seal)" } : undefined}
          title="Records this answer on the case. Nothing is sent."
        >
          {busy === "yes" ? "Recording" : choices.yes}
        </button>
        {given ? (
          <span className="micro">
            you answered {given === "yes" ? choices.yes.toLowerCase() : choices.no.toLowerCase()},
            and you can change it
          </span>
        ) : null}
      </div>
      <p
        className="data mt-4 max-w-[66ch]"
        style={{ color: failed ? "var(--alarm)" : "var(--ink-2)" }}
      >
        {note ??
          "Answering sends nothing and renews nothing. It puts the one fact Lapse cannot read anywhere on the record, and a pass then works out which filing is right and drafts it for you to approve."}
      </p>
    </div>
  );
}
