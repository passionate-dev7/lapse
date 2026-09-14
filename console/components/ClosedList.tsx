import { itemLabel, STATUS_WORD, type Case } from "@/lib/cases";
import { longDate, plural, titleCase } from "@/lib/format";

/**
 * Cases that are no longer decisions. This sits under the queue as well as under the empty
 * state, because the card a person just approved leaves the queue the moment they press the
 * button, and a thing that vanishes with no receipt is indistinguishable from a thing that
 * failed. A filed row prints the delivery message id, which is the only proof a response left.
 */
export function ClosedList({ cases, heading }: { cases: Case[]; heading: string }) {
  const closed = cases
    .filter((c) => c.status === "filed" || c.status === "dismissed")
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));

  if (!closed.length) return null;
  const shown = closed.slice(0, 6);

  return (
    <div className="mt-16">
      <h2 className="label">{heading}</h2>
      <ul className="mt-5 border-t border-rule">
        {shown.map((c) => (
          <li
            key={c.case_id}
            className="grid grid-cols-1 gap-x-6 gap-y-1 border-b border-rule py-4 sm:grid-cols-[150px_1fr_auto] sm:items-baseline"
          >
            <span className="micro">{longDate(c.updated_at?.slice(0, 10))}</span>
            <span className="prose-16">
              {titleCase(c.item?.address) || itemLabel(c.item ?? {}) || c.case_id}
              <span className="micro" style={{ marginLeft: "10px" }}>
                {itemLabel(c.item ?? {})}
              </span>
            </span>
            <span
              className="micro min-w-0"
              style={{
                color: c.status === "filed" ? "var(--seal)" : "var(--ink-2)",
                // An SES message id is 60 characters of mono and there is no space in it, so
                // without this it runs off the right edge of a phone.
                overflowWrap: "anywhere",
              }}
            >
              {c.status === "filed" && c.delivery?.message_id
                ? `filed, ${c.delivery.message_id}`
                : STATUS_WORD[c.status]}
            </span>
          </li>
        ))}
      </ul>
      {closed.length > shown.length ? (
        <p className="micro mt-4">{plural(closed.length - shown.length, "older case")} not shown.</p>
      ) : null}
    </div>
  );
}
