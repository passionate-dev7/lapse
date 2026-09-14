import { ChoiceAnswer, DateAnswer } from "@/components/AnswerAction";
import { ApproveAction } from "@/components/ApproveAction";
import { ChecksTable } from "@/components/ChecksTable";
import {
  answerChoices,
  answerShape,
  decisionText,
  headline,
  itemLabel,
  klassTone,
  recordedAnswer,
  type Case,
} from "@/lib/cases";
import { daysPhrase, hostOf, longDate, squash, tailOf } from "@/lib/format";

/**
 * One decision, ordered by what a person needs in the order they need it: how long they have,
 * where it is, what it is, what the engine checked, what it wrote, and then the one thing they
 * can do about it.
 *
 * The day count is the largest thing on the card. That is the variable this product exists to
 * report, and it used to be set at 13px underneath a 25px line that repeated the same rulebook
 * sentence on every card of the same permit type.
 */
export function QueueCard({ item: c, filingEnabled }: { item: Case; filingEnabled: boolean }) {
  const v = c.verdict;
  const tone = klassTone(v.klass);
  const identifiers = itemLabel(c.item);
  const decision = decisionText(c);
  const answer = recordedAnswer(c);
  const shape = answerShape(c);
  const choices = answerChoices(c);

  // DOB writes in block capitals. It is quoted as it was published, in the mono, because the
  // serif on this page is what Lapse says and the mono is what it can show you.
  const work = squash(c.item.kind === "violation" ? c.item.description : c.job?.description);

  const dataset = tailOf(c.item.source);

  return (
    <article className="record">
      <div className="grid grid-cols-1 gap-x-8 gap-y-5 lg:grid-cols-[minmax(0,1fr)_212px]">
        <div className="lg:order-2 lg:border-l lg:border-rule lg:pl-6 lg:pt-1">
          <p className="anchor" style={{ color: tone }}>
            {daysPhrase(v.days_remaining)}
          </p>
          <p className="label mt-2.5" style={{ color: tone }}>
            {v.klass ?? "no class"}
          </p>
          <p className="micro mt-2">
            {v.due_on ? `due ${longDate(v.due_on)}` : "no date on record"}
          </p>
          {v.anchor_name ? <p className="micro">counted from {v.anchor_name}</p> : null}
        </div>

        <div className="min-w-0 lg:order-1">
          <h2 className="record-title max-w-[34ch]">{headline(c)}</h2>
          <p className="micro mt-2">
            {[
              c.item.kind ?? c.kind,
              identifiers,
              c.item.bin ? `BIN ${c.item.bin}` : "",
            ]
              .filter(Boolean)
              .join("  ·  ")}
          </p>

          {decision ? (
            <p className="decision mt-5 max-w-[60ch]">{decision}</p>
          ) : null}

          {work ? (
            <div className="mt-6">
              <h3 className="label">
                {c.item.kind === "violation" ? "What DOB wrote on it" : "The work this permit covers"}
              </h3>
              <p className="data mt-2 max-w-[66ch]" style={{ color: "var(--ink-2)" }}>
                {work}
              </p>
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
          ) : shape === "yes_no" && choices.length ? (
            <ChoiceAnswer caseId={c.case_id} choices={choices} answer={answer} />
          ) : shape === "date" ? (
            <DateAnswer caseId={c.case_id} answer={answer} />
          ) : (
            <p className="data mt-7 max-w-[66ch]" style={{ color: "var(--ink-2)" }}>
              This question does not have a set of answers Lapse can offer you here, so there is
              no control on this card that would do anything. It is on the record and a pass will
              carry it. Nothing is drafted and nothing will be sent from this page.
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
            {v.evidence_id ? (
              <span style={{ overflowWrap: "anywhere" }}>{v.evidence_id}</span>
            ) : null}
          </p>
        </div>
      </div>
    </article>
  );
}
