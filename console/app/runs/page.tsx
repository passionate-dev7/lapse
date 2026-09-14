import type { Metadata } from "next";
import Link from "next/link";

import { ProblemState } from "@/components/ProblemState";
import { Provenance } from "@/components/Provenance";
import { Cadence, RunHistory } from "@/components/RunHistory";
import { byNewest, isSweep, latestSweep } from "@/lib/cases";
import { longDate, plural, stampUTC, titleCase } from "@/lib/format";
import { CONTRACTOR, listCases, schedule } from "@/lib/store";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Lapse: every screening pass on record",
};

export default async function RunsPage() {
  const { cases, runs, origin, problem } = await listCases();

  if (problem) {
    return (
      <>
        <ProblemState problem={problem} />
        <Provenance origin={origin} cases={cases.length} runs={runs.length} />
      </>
    );
  }

  const ordered = byNewest(runs);
  const sweeps = ordered.filter(isSweep);
  const newest = latestSweep(runs);

  return (
    <>
      <section className="pt-12">
        <p className="micro">
          <Link className="cite" href="/">
            back to the decisions
          </Link>
        </p>
        <h1 className="statement mt-5 max-w-[24ch]">
          {ordered.length
            ? `${plural(ordered.length, "pass")} on record, ${sweeps.length} of them over the whole portfolio.`
            : "No pass has written a summary yet."}
        </h1>
        <p className="prose-16 mt-6 max-w-[64ch]" style={{ color: "var(--ink-2)" }}>
          {`Each row is one run of the agent against ${titleCase(CONTRACTOR)}. A sweep reads every permit and every open violation on the portfolio; a single case filing is the pass an approval starts, narrowed to the one item it was approved for. Both screen, both are counted, and neither is allowed to speak for the other.`}
        </p>
        {newest ? (
          <p className="data mt-5 max-w-[64ch]" style={{ color: "var(--ink-2)" }}>
            {`The newest sweep finished ${stampUTC(newest.finished_at)}, reading the city as of ${longDate(newest.as_of)} from ${newest.source}.`}
          </p>
        ) : null}
        <Cadence schedule={schedule()} />
      </section>

      <RunHistory runs={runs} heading="Every pass, newest first" />

      <Provenance origin={origin} cases={cases.length} runs={runs.length} />
    </>
  );
}
