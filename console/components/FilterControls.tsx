"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SORTS, SORT_WORD, toQuery, withPatch, type Filter, type Sort } from "@/lib/view";

/**
 * The two controls that cannot be a link, because a link needs the value before it is written.
 * Both push a URL rather than holding state, so the address bar is the only place a filter
 * lives and a link to a filtered queue opens the same queue for the next person.
 */

export function SearchBox({ filter }: { filter: Filter }) {
  const router = useRouter();
  const [text, setText] = useState(filter.q);

  // The URL is the source of truth. Pressing a class chip or the clear link changes it without
  // going through this input, and the box has to follow rather than keep the old word.
  useEffect(() => setText(filter.q), [filter.q]);

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        router.push(toQuery(withPatch(filter, { q: text.trim() })));
      }}
    >
      <label className="label sr-only" htmlFor="queue-search">
        Search the queue
      </label>
      <input
        id="queue-search"
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="address, job number, BIN, wording"
        className="data w-full min-w-0 rounded-[4px] border px-3 py-[9px] sm:w-[268px]"
        style={{
          borderColor: "var(--rule-strong)",
          background: "var(--sheet)",
          color: "var(--ink)",
        }}
      />
      <button type="submit" className="btn btn-secondary">
        Find
      </button>
    </form>
  );
}

export function SortSelect({ filter }: { filter: Filter }) {
  const router = useRouter();
  return (
    <label className="flex items-center gap-2">
      <span className="label">Order</span>
      <select
        value={filter.sort}
        onChange={(e) => router.push(toQuery(withPatch(filter, { sort: e.target.value as Sort })))}
        className="data rounded-[4px] border px-2.5 py-[8px]"
        style={{
          borderColor: "var(--rule-strong)",
          background: "var(--sheet)",
          color: "var(--ink)",
        }}
      >
        {SORTS.map((s) => (
          <option key={s} value={s}>
            {SORT_WORD[s]}
          </option>
        ))}
      </select>
    </label>
  );
}
