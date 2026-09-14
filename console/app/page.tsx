import type { Metadata } from "next";

import { EmptyQueue } from "@/components/EmptyQueue";
import { ProblemState } from "@/components/ProblemState";
import { Provenance } from "@/components/Provenance";
import { QueueCard } from "@/components/QueueCard";
import { heldSentence, latestRun, queue, runSentence } from "@/lib/cases";
import { titleCase } from "@/lib/format";
import { CONTRACTOR, filingFunction, listCases } from "@/lib/store";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Lapse: DOB deadline queue",
};

const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

export default async function QueuePage() {
  const { cases, runs, origin, problem } = await listCases();

  if (problem) {
    return (
      <>
        <ProblemState problem={problem} />
        <Provenance origin={origin} cases={cases.length} runs={runs.length} />
      </>
    );
  }

  const run = latestRun(runs);
  const pending = queue(cases);

  if (!pending.length) {
    return (
      <>
        <EmptyQueue cases={cases} run={run} contractor={CONTRACTOR} />
        <Provenance origin={origin} cases={cases.length} runs={runs.length} />
      </>
    );
  }

  const word = WORDS[pending.length] ?? String(pending.length);
  const held = heldSentence(run);

  return (
    <>
      <section className="pt-12">
        <h1 className="statement max-w-[22ch]">
          {word} {pending.length === 1 ? "decision is" : "decisions are"} yours to make.
        </h1>
        <p className="prose-16 mt-6 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
          {runSentence(run, titleCase(CONTRACTOR))}
        </p>
        {held ? (
          <p className="data mt-5 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
            {held}
          </p>
        ) : null}
      </section>

      <section className="mt-10 border-t border-rule">
        {pending.map((item) => (
          <QueueCard key={item.case_id} item={item} filingEnabled={Boolean(filingFunction())} />
        ))}
      </section>

      <Provenance origin={origin} cases={cases.length} runs={runs.length} />
    </>
  );
}
