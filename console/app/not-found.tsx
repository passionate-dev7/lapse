import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Lapse: no such page",
};

export default function NotFound() {
  return (
    <section className="pt-24">
      <h1 className="statement max-w-[20ch]">There is nothing at this address.</h1>
      <p className="prose-16 mt-6 max-w-[58ch]" style={{ color: "var(--ink-2)" }}>
        Lapse has one screen, and it is the queue of decisions that are actually yours. Everything
        else the agent does, it does without opening a page.
      </p>
      <p className="mt-8">
        <Link href="/" className="btn btn-secondary">
          Back to the queue
        </Link>
      </p>
    </section>
  );
}
