import { plural, stampUTC } from "@/lib/format";
import { CONTRACTOR, REGION, TABLE, type Origin } from "@/lib/store";

/**
 * Where the figures above came from. A number with no origin is a rumour with good posture, so
 * every page ends by naming the table, the region, the partition and the moment it was read.
 */
export function Provenance({
  origin,
  cases,
  runs,
}: {
  origin: Origin;
  cases: number;
  runs: number;
}) {
  const from =
    origin === "preview"
      ? `a local preview file standing in for DynamoDB table ${TABLE}, which is a developer mode and never runs in production`
      : `DynamoDB table ${TABLE} in ${REGION}`;
  return (
    <p className="micro mt-20 border-t border-rule pt-6 max-w-[86ch]">
      {`${plural(cases, "case")} and ${plural(runs, "run record")} read from ${from}, partition ${CONTRACTOR}, at ${stampUTC(new Date().toISOString())}.`}
    </p>
  );
}
