const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** DOB dates arrive as bare YYYY-MM-DD. Parsing those with Date() lands on the day before
 *  in any timezone west of UTC, so the calendar parts are read off the string itself. */
export function longDate(value: string | null | undefined): string {
  if (!value) return "";
  const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!parts) return value;
  const month = MONTHS[Number(parts[2]) - 1];
  if (!month) return value;
  return `${month} ${Number(parts[3])}, ${parts[1]}`;
}

export function stampUTC(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

export function ago(iso: string, now = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const mins = Math.max(0, Math.round((now - then) / 60_000));
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.round(hours / 24);
  if (days < 60) return `${days} days ago`;
  return `${Math.round(days / 30)} months ago`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}

/**
 * Reads `verdict.days_remaining` out loud. The number is never recomputed from the due date,
 * because the engine counted it against the day it ran and the browser would count it against
 * the reader's clock, which is a different question with a similar answer.
 */
export function daysPhrase(days: number | null | undefined): string {
  if (days === null || days === undefined) return "no clock on this one";
  if (days < 0) return `${plural(Math.abs(days), "day")} late`;
  if (days === 0) return "due today";
  return `${plural(days, "day")} left`;
}

/** DOB pads its free text to a fixed column width, so it arrives with runs of spaces in it. */
export function squash(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

export function sentenceCase(text: string): string {
  const clean = squash(text);
  if (!clean) return "";
  return `${clean.charAt(0).toUpperCase()}${clean.slice(1)}`;
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return "";
  }
}

/** The last path segment, which on an Open Data link is the dataset id, eg `ipu4-2q9a`. */
export function tailOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    const segments = new URL(url).pathname.split("/").filter(Boolean);
    return segments[segments.length - 1] ?? "";
  } catch {
    return "";
  }
}

/** DOB writes addresses and descriptions in block capitals. Shouting is the dataset's, not ours. */
export function titleCase(text: string | null | undefined): string {
  const clean = squash(text);
  if (!clean) return "";
  if (clean !== clean.toUpperCase()) return clean;
  return clean
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Of|And|The|At|On|In|To)\b/g, (m) => m.toLowerCase());
}
