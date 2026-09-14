import { ApproveAction } from "@/components/ApproveAction";
import { ChecksTable } from "@/components/ChecksTable";
import { headline, itemLabel, klassTone, type Case } from "@/lib/cases";
import {
  daysPhrase,
  hostOf,
  longDate,
  splitStatement,
  squash,
  tailOf,
  titleCase,
} from "@/lib/format";

/**
 * One decision. The rail on the right is the deadline and nothing else, so the page has a spine
 * a person can run their eye down without reading a word. The reading column answers, in order:
 * what to do, which item, what the work is, what the engine checked, what it wrote, and where
 * the date came from.
 */
export function QueueCard({ item: c, filingEnabled }: { item: Case; filingEnabled: boolean }) {
  const v = c.verdict;
  const tone = klassTone(v.klass);
  const identifiers = itemLabel(c.item);
  const address = titleCase(c.item.address);

  // DOB writes in block capitals. It is quoted as it was published, in the mono, because the
  // serif on this page is what Lapse says and the mono is what it can show you.
  const work = squash(
    c.item.kind === "violation" ? c.item.description : c.job?.description,
  );

  const dataset = tailOf(c.item.source);
  const [statement, rest] = splitStatement(headline(c));

  return (
    <article className="record">
      <div className="grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-[1fr_212px]">
        <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 lg:order-2 lg:flex-col lg:items-end lg:gap-y-2 lg:pt-2 lg:text-right">
          <span className="label" style={{ color: tone }}>
            {v.klass ?? "no class"}
          </span>
          <span className="data" style={{ color: tone }}>
            {daysPhrase(v.days_remaining)}
          </span>
          <span className="micro">{v.due_on ? `due ${longDate(v.due_on)}` : "no date on record"}</span>
          {v.anchor_name ? <span className="micro">counted from {v.anchor_name}</span> : null}
        </div>

        <div className="min-w-0 lg:order-1">
          <h2 className="record-title max-w-[44ch]">{statement}</h2>
          {rest ? (
            <p className="prose-16 mt-3 max-w-[64ch]" style={{ color: "var(--ink-2)" }}>
              {rest}
            </p>
          ) : null}

          <p className="data mt-4" style={{ color: "var(--ink)" }}>
            <span style={{ textTransform: "capitalize" }}>{c.item.kind ?? c.kind}</span>
            {address ? ` at ${address}` : ""}
          </p>
          {identifiers || c.item.bin ? (
            <p className="micro mt-1">
              {[identifiers, c.item.bin ? `BIN ${c.item.bin}` : ""].filter(Boolean).join("  ·  ")}
            </p>
          ) : null}

          {work ? (
            <div className="mt-6">
              <h3 className="label">
                {c.item.kind === "violation" ? "What DOB wrote on it" : "The work this permit covers"}
              </h3>
              <p className="data mt-2 max-w-[74ch]" style={{ color: "var(--ink-2)" }}>
                {work}
              </p>
            </div>
          ) : null}

          {v.missing.length ? (
            <div className="mt-6">
              <h3 className="label">What the engine could not settle</h3>
              <ul className="mt-2 max-w-[74ch]">
                {v.missing.map((m) => (
                  <li key={m} className="data" style={{ color: "var(--ink-2)" }}>
                    {squash(m)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-7">
            <h3 className="label">What the engine checked</h3>
            <ChecksTable checks={v.checks} />
          </div>

          {c.status === "awaiting_approval" && c.draft_text ? (
            <div className="mt-8">
              <h3 className="label">The drafted response, in full</h3>
              {v.artifact ? <p className="micro mt-2">Files as {v.artifact}</p> : null}
              <div className="draft mt-3 max-w-[78ch]">{c.draft_text}</div>
            </div>
          ) : null}

          {c.status === "awaiting_approval" ? (
            <ApproveAction caseId={c.case_id} enabled={filingEnabled} />
          ) : (
            <p className="data mt-7 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
              Nothing is drafted for this one and nothing will be sent from this page. Lapse needs
              the answer above before it can tell which filing is the right one.
            </p>
          )}

          <p className="micro mt-6 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
            {v.citation ? (
              <a className="cite" href={v.citation} target="_blank" rel="noreferrer">
                the published rule this deadline comes from
              </a>
            ) : (
              <span style={{ color: "var(--alarm)" }}>
                no rule citation on this record, so the date is unsupported
              </span>
            )}
            {c.item.url ? (
              <a className="cite" href={c.item.url} target="_blank" rel="noreferrer">
                DOB record on {hostOf(c.item.url)}
              </a>
            ) : null}
            {c.item.source ? (
              <a className="cite" href={c.item.source} target="_blank" rel="noreferrer">
                {dataset ? `Open Data ${dataset}` : "the Open Data table"}
              </a>
            ) : null}
            {v.evidence_id ? <span>{v.evidence_id}</span> : null}
          </p>
        </div>
      </div>
    </article>
  );
}
