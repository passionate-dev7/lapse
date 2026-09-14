import type { Problem } from "@/lib/store";

/**
 * Not an error page. It is the difference between "you are clear" and "nobody looked", which on
 * a deadline product is the whole difference. It never borrows the calm of the empty state.
 */
export function ProblemState({ problem }: { problem: Problem }) {
  return (
    <section className="report-in pt-20">
      <h1 className="statement max-w-[22ch]">{problem.headline}</h1>
      <p className="prose-16 mt-7 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
        {problem.detail}
      </p>
      <p
        className="data mt-8 max-w-[62ch] border-l-2 pl-4"
        style={{ borderColor: "var(--alarm)", color: "var(--ink-2)" }}
      >
        Treat this screen as blank. Permits expire on their own schedule whether or not anything
        here is reading them.
      </p>
    </section>
  );
}
