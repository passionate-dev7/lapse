import type { Metadata } from "next";

import { ClosedList } from "@/components/ClosedList";
import { EmptyQueue } from "@/components/EmptyQueue";
import { FilterBar, NoMatches } from "@/components/FilterBar";
import { Overview, WorstLine } from "@/components/Overview";
import { OperatorStrip } from "@/components/OperatorStrip";
import { ProblemState } from "@/components/ProblemState";
import { Provenance } from "@/components/Provenance";
import { QueueCard } from "@/components/QueueCard";
import { QueueList, type Approvable, type Destination } from "@/components/QueueList";
import { Cadence, RunHistory } from "@/components/RunHistory";
import { heldSentence, itemLabel, latestSweep, queue, runSentence, type Case } from "@/lib/cases";
import { daysPhrase, longDate, squash, titleCase } from "@/lib/format";
import { CONTRACTOR, filingFunction, listCases, schedule } from "@/lib/store";
import { applyFilter, overview, parseFilter, type RawParams } from "@/lib/view";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Lapse: DOB deadline queue",
};

const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}) {
  const [params, read] = await Promise.all([searchParams, listCases()]);
  const { cases, runs, origin, problem } = read;

  if (problem) {
    return (
      <>
        <ProblemState problem={problem} />
        <Provenance origin={origin} cases={cases.length} runs={runs.length} />
      </>
    );
  }

  // The newest record that describes a sweep, not simply the newest record. Approving writes a
  // run record of its own, and quoting that one makes the headline report a pass over the whole
  // portfolio that opened the single case the reader just approved.
  const run = latestSweep(runs);
  const pending = queue(cases);

  if (!pending.length) {
    return (
      <>
        <EmptyQueue cases={cases} run={run} contractor={CONTRACTOR} />
        <RunHistory runs={runs} limit={4} heading="What ran while nobody was watching" />
        <Cadence schedule={schedule()} />
        <Provenance origin={origin} cases={cases.length} runs={runs.length} />
      </>
    );
  }

  const filter = parseFilter(params);
  const shape = overview(cases);
  const visible = applyFilter(pending, filter);

  const word = WORDS[pending.length] ?? String(pending.length);
  const held = heldSentence(run);
  const filing = filingFunction();

  const approvable: Approvable[] = visible
    .filter((c) => c.status === "awaiting_approval")
    .map((c) => ({
      case_id: c.case_id,
      place: titleCase(c.item?.address) || itemLabel(c.item ?? {}) || c.case_id,
      identifiers: itemLabel(c.item ?? {}),
      klass: c.verdict?.klass ?? "no class",
      clock: daysPhrase(c.verdict?.days_remaining),
      artifact: squash(c.verdict?.artifact),
      draft: squash(c.draft_text),
    }));

  return (
    <>
      <OperatorStrip
        pending={pending.length}
        worst={shape.worst}
        run={run}
        contractor={CONTRACTOR}
        lapsed={shape.byClass.find((b) => b.klass === "lapsed")?.count ?? 0}
      />

      <section className="pt-8">
        <WorstLine worst={shape.worst} />
        {filing ? null : (
          <p
            className="data mt-6 max-w-[62ch] border-l-2 pl-4"
            style={{ borderColor: "var(--rule-strong)", color: "var(--ink-2)" }}
          >
            Approve is off on this deployment. LAPSE_AGENT_FUNCTION names the function that
            actually files a response, and it is unset here, so the drafts below can be read and
            checked but not sent. Said once rather than on every card.
          </p>
        )}
      </section>

      <Overview shape={shape} filter={filter} />

      <FilterBar
        filter={filter}
        pending={pending}
        shown={visible.length}
        sites={shape.boroughs.map((b) => b.site)}
      />

      {visible.length ? (
        <QueueList
          rows={visible.map((c) => ({
            case_id: c.case_id,
            approvable: c.status === "awaiting_approval",
            card: <QueueCard item={c} filingEnabled={Boolean(filing)} />,
          }))}
          approvable={approvable}
          destination={lastDelivery(cases)}
          filingEnabled={Boolean(filing)}
        />
      ) : (
        <NoMatches filter={filter} total={pending.length} />
      )}

      <RunHistory runs={runs} limit={4} heading="What ran while nobody was watching" />
      <Cadence schedule={schedule()} />

      <ClosedList cases={cases} heading="Already closed" />

      <Provenance origin={origin} cases={cases.length} runs={runs.length} />
    </>
  );
}

/**
 * Where the last response this console filed actually went, read off the delivery block the
 * filing function wrote on the case it filed. A batch confirmation has to name a recipient, and
 * the only honest one available to a page that cannot see SES is the last real send.
 */
function lastDelivery(cases: Case[]): Destination | null {
  const filed = cases
    .filter((c) => c.status === "filed" && c.delivery?.to)
    .sort((a, b) => (b.delivery?.sent_at ?? "").localeCompare(a.delivery?.sent_at ?? ""));
  const d = filed[0]?.delivery;
  if (!d?.to) return null;
  return {
    to: d.to,
    intended: d.intended ?? d.to,
    reason: squash(d.reason) || "the filing function recorded no reason for that recipient",
    when: d.sent_at ? longDate(d.sent_at.slice(0, 10)) : "a date the record does not carry",
  };
}
