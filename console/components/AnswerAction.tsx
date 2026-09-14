"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Answer, Choice } from "@/lib/cases";
import { longDate } from "@/lib/format";

function useAnswer(caseId: string) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function send(value: string) {
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

  return { busy, note, failed, send };
}

function Note({ note, failed, fallback }: { note: string | null; failed: boolean; fallback: string }) {
  return (
    <p
      className="data mt-4 max-w-[66ch]"
      style={{ color: failed ? "var(--alarm)" : "var(--ink-2)" }}
    >
      {note ?? fallback}
    </p>
  );
}

/**
 * The answer to a question that has two values. They are the two values of one decision, not two
 * actions competing for the card, so they are a matched pair in the same weight and neither is
 * the primary. There is no third button: leaving it alone is already how you decline to answer,
 * and a Skip control would be a second action that does nothing.
 *
 * The labels come off `verdict.choices`, which is the city's framing of what each answer means.
 * Nothing here sends anything, and the copy says so before and after.
 */
export function ChoiceAnswer({
  caseId,
  choices,
  answer,
}: {
  caseId: string;
  choices: Choice[];
  answer: Answer | null;
}) {
  const { busy, note, failed, send } = useAnswer(caseId);
  const given = answer?.value ?? null;

  return (
    <div className="mt-7">
      <div className="flex flex-wrap items-center gap-3">
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            className="btn btn-secondary"
            disabled={busy !== null}
            onClick={() => send(choice.value)}
            style={
              given === choice.value
                ? { borderColor: "var(--seal)", color: "var(--seal)" }
                : undefined
            }
            title="Records this answer on the case. Nothing is sent."
          >
            {busy === choice.value ? "Recording" : choice.label}
          </button>
        ))}
        {given ? <span className="micro">recorded, and you can change it</span> : null}
      </div>
      <Note
        note={note}
        failed={failed}
        fallback="Answering sends nothing and renews nothing. It puts the one fact Lapse cannot read anywhere on the record, and the next pass works out which filing is right and drafts it for you to approve."
      />
    </div>
  );
}

/**
 * The answer to a question that asks for a date. These are the violations where DOB publishes a
 * cure path and no deadline, so the engine refuses to invent one and hands the clock back.
 *
 * The reason is on screen, because "when do you plan to respond" reads like a nag otherwise. The
 * contractor sets the date once and it becomes the anchor the four classes are cut from, so the
 * item goes quiet until it is actually close.
 */
export function DateAnswer({
  caseId,
  answer,
}: {
  caseId: string;
  answer: Answer | null;
}) {
  const { busy, note, failed, send } = useAnswer(caseId);
  const given = answer?.value ?? null;
  const today = new Date().toISOString().slice(0, 10);
  const [value, setValue] = useState(given && /^\d{4}-\d{2}-\d{2}$/.test(given) ? given : "");

  return (
    <div className="mt-7">
      <label className="label" htmlFor={`by-${caseId}`}>
        The date you intend to respond by
      </label>
      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <input
          id={`by-${caseId}`}
          type="date"
          className="field"
          style={{ width: "auto", minWidth: "190px" }}
          value={value}
          min={today}
          onChange={(e) => setValue(e.target.value)}
        />
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null || !value || value < today}
          onClick={() => send(value)}
          title={
            !value
              ? "Pick a date first"
              : value < today
                ? "The date has to be today or later"
                : "Records this date on the case. Nothing is sent."
          }
        >
          {busy ? "Recording" : "Set the date"}
        </button>
        {given && /^\d{4}-\d{2}-\d{2}$/.test(given) ? (
          <span className="micro">now tracked to {longDate(given)}</span>
        ) : null}
      </div>
      <Note
        note={note}
        failed={failed}
        fallback="DOB publishes a cure path for this one and no deadline, so Lapse will not invent a date and this clock is yours to set. Once it is set, Lapse tracks it like any other deadline and goes quiet until it is close. Nothing is sent."
      />
    </div>
  );
}
