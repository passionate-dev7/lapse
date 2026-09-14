"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState, type ReactNode } from "react";

/**
 * Selection and batch approval over the rendered queue.
 *
 * Batch approval is permission to send responses that already passed every check, never a way
 * to skip checking. Each selected case goes through the same single case endpoint one at a
 * time, so the status condition, the item id read back off the record and the veto the filing
 * function runs all apply to every one of them exactly as they do to a single press. Nothing
 * here writes to the table and nothing here can file: it presses the same button faster.
 */

export interface Approvable {
  case_id: string;
  place: string;
  identifiers: string;
  klass: string;
  clock: string;
  artifact: string;
  draft: string;
}

export interface Destination {
  to: string;
  intended: string;
  reason: string;
  when: string;
}

export interface Row {
  case_id: string;
  approvable: boolean;
  card: ReactNode;
}

type Outcome = { case_id: string; ok: boolean; message: string };

export function QueueList({
  rows,
  approvable,
  destination,
  filingEnabled,
}: {
  rows: Row[];
  approvable: Approvable[];
  destination: Destination | null;
  filingEnabled: boolean;
}) {
  const router = useRouter();
  const [picked, setPicked] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [current, setCurrent] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  // The batch as it stood when Send was pressed. A finished run clears the selection, and the
  // report of what happened has to survive that: a list that empties itself at the moment a
  // person wants to read it is how an approval becomes something they have to take on trust.
  const [batch, setBatch] = useState<Approvable[]>([]);

  const byId = useMemo(() => new Map(approvable.map((a) => [a.case_id, a])), [approvable]);
  const selected = useMemo(
    () => picked.map((id) => byId.get(id)).filter((a): a is Approvable => Boolean(a)),
    [picked, byId],
  );

  const toggle = useCallback((id: string) => {
    setPicked((was) => (was.includes(id) ? was.filter((x) => x !== id) : [...was, id]));
  }, []);

  const allShown = approvable.map((a) => a.case_id);
  const everyOne = allShown.length > 0 && allShown.every((id) => picked.includes(id));

  async function send() {
    const batched = selected;
    setBatch(batched);
    setSending(true);
    setOutcomes([]);
    const done: Outcome[] = [];
    for (const item of batched) {
      setCurrent(item.case_id);
      try {
        const res = await fetch(`/api/cases/${encodeURIComponent(item.case_id)}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ action: "approve" }),
        });
        const body = (await res.json()) as { error?: string; message?: string };
        done.push({
          case_id: item.case_id,
          ok: res.ok,
          message: res.ok
            ? (body.message ?? "Approval recorded and handed to the filing function.")
            : (body.error ?? `The write failed with status ${res.status}.`),
        });
      } catch (error) {
        done.push({ case_id: item.case_id, ok: false, message: (error as Error).message });
      }
      setOutcomes([...done]);
    }
    setCurrent(null);
    setSending(false);
    setPicked(done.filter((d) => !d.ok).map((d) => d.case_id));
    router.refresh();
  }

  return (
    <>
      {approvable.length > 1 ? (
        <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-rule pt-5">
          <label className="flex cursor-pointer items-center gap-2.5">
            <input
              type="checkbox"
              className="pick"
              checked={everyOne}
              onChange={() => setPicked(everyOne ? [] : allShown)}
            />
            <span className="data" style={{ color: "var(--ink)" }}>
              Select the {approvable.length} drafts on this list
            </span>
          </label>
          <span className="micro" style={{ color: "var(--ink-2)" }}>
            The other {rows.length - approvable.length} need an answer from you first and cannot be
            batched.
          </span>
        </div>
      ) : null}

      <section className="mt-6 border-t border-rule">
        {rows.map((row) => (
          <div key={row.case_id}>
            {row.approvable ? (
              <label
                className="flex cursor-pointer items-center gap-2.5 pt-7"
                style={{ marginBottom: "-14px" }}
              >
                <input
                  type="checkbox"
                  className="pick"
                  checked={picked.includes(row.case_id)}
                  onChange={() => toggle(row.case_id)}
                />
                <span className="label">
                  {picked.includes(row.case_id) ? "in this batch" : "add to a batch"}
                </span>
              </label>
            ) : null}
            {row.card}
          </div>
        ))}
      </section>

      {picked.length ? (
        <div className="tray mt-0">
          <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-4">
            <p className="data" style={{ color: "var(--ink)" }}>
              {picked.length === 1
                ? "1 drafted response selected."
                : `${picked.length} drafted responses selected.`}
              <span style={{ color: "var(--ink-2)" }}>
                {" "}
                Nothing has been sent and nothing is written until you confirm.
              </span>
            </p>
            <div className="flex items-center gap-3">
              <button type="button" className="btn btn-secondary" onClick={() => setPicked([])}>
                Clear
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!filingEnabled}
                onClick={() => {
                  setOutcomes([]);
                  setBatch([]);
                  setOpen(true);
                }}
                title={
                  filingEnabled
                    ? "Opens the list of exactly what would be filed, before anything is written"
                    : "LAPSE_AGENT_FUNCTION is not set on this deployment, so nothing here could be filed"
                }
              >
                Review {picked.length} and send
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {open ? (
        <Confirm
          selected={outcomes.length || sending ? batch : selected}
          destination={destination}
          sending={sending}
          current={current}
          outcomes={outcomes}
          onDrop={toggle}
          onClose={() => setOpen(false)}
          onSend={send}
        />
      ) : null}
    </>
  );
}

function Confirm({
  selected,
  destination,
  sending,
  current,
  outcomes,
  onDrop,
  onClose,
  onSend,
}: {
  selected: Approvable[];
  destination: Destination | null;
  sending: boolean;
  current: string | null;
  outcomes: Outcome[];
  onDrop: (id: string) => void;
  onClose: () => void;
  onSend: () => void;
}) {
  const result = new Map(outcomes.map((o) => [o.case_id, o]));
  const finished = outcomes.length > 0 && !sending;
  const failures = outcomes.filter((o) => !o.ok).length;

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto px-4 py-8 sm:px-6 sm:py-12"
      style={{ background: "var(--scrim)" }}
      role="dialog"
      aria-modal="true"
      aria-label="Confirm the batch"
    >
      <div className="sheet-panel report-in mx-auto w-full max-w-[760px] p-7 sm:p-9">
        <h2 className="record-title max-w-[40ch]">
          {finished
            ? failures
              ? `${outcomes.length - failures} of ${outcomes.length} were handed to the filing function.`
              : `${outcomes.length === 1 ? "One response" : `${outcomes.length} responses`} handed to the filing function.`
            : `Send ${selected.length === 1 ? "this response" : `these ${selected.length} responses`}?`}
        </h2>

        {finished ? null : (
          <p className="prose-16 mt-4 max-w-[64ch]" style={{ color: "var(--ink-2)" }}>
            Each one is filed on its own pass. The case has to still be waiting for approval when
            the pass reaches it, the DOB item id is read back off the record rather than from this
            page, and the send is vetoed unless the drafted text is the text that was checked.
            Approving in a batch does not skip any of that.
          </p>
        )}

        {destination && !finished ? (
          <p className="data mt-4 max-w-[64ch] border-l-2 pl-4" style={{ borderColor: "var(--rule-strong)", color: "var(--ink-2)" }}>
            {`The last response this console filed went to ${destination.to} on ${destination.when}. ${destination.reason}. The filing function resolves the recipient again at send time and writes the message id it gets back, so it is that record, not this page, that proves where these land.`}
          </p>
        ) : null}

        <ul className="mt-7 border-t border-rule">
          {selected.map((item) => {
            const out = result.get(item.case_id);
            return (
              <li key={item.case_id} className="border-b border-rule py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-2">
                  <span className="data" style={{ color: "var(--ink)" }}>
                    {item.place}
                  </span>
                  {sending || finished ? (
                    <span
                      className="label"
                      style={{
                        color: out ? (out.ok ? "var(--seal)" : "var(--alarm)") : "var(--ink-3)",
                      }}
                    >
                      {out ? (out.ok ? "handed off" : "refused") : current === item.case_id ? "sending" : "queued"}
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="micro"
                      style={{ color: "var(--seal)", textDecoration: "underline", textUnderlineOffset: "3px" }}
                      onClick={() => onDrop(item.case_id)}
                    >
                      take out of the batch
                    </button>
                  )}
                </div>
                <p className="micro mt-1.5">
                  {[item.identifiers, `${item.klass}, ${item.clock}`].filter(Boolean).join("  ·  ")}
                </p>
                {item.artifact ? (
                  <p className="micro mt-1.5" style={{ color: "var(--ink-2)" }}>
                    Files as {item.artifact}
                  </p>
                ) : null}
                {out ? (
                  <p
                    className="micro mt-2 max-w-[70ch]"
                    style={{ color: out.ok ? "var(--ink-2)" : "var(--alarm)" }}
                  >
                    {out.message}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          {finished ? (
            <button type="button" className="btn btn-primary" onClick={onClose}>
              Close
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-primary"
                disabled={sending || !selected.length}
                onClick={onSend}
              >
                {sending
                  ? `Sending ${outcomes.length + 1} of ${selected.length}`
                  : `Approve and file ${selected.length}`}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={sending}
                onClick={onClose}
              >
                Not now
              </button>
            </>
          )}
        </div>

        {finished ? (
          <p className="micro mt-5 max-w-[70ch]" style={{ color: "var(--ink-2)" }}>
            A case turns to filed, with a message id on it, only when the filing function reports
            that a response actually left. Until then it is an accepted request, and the closed
            list below is where the receipt shows up.
          </p>
        ) : null}
      </div>
    </div>
  );
}
