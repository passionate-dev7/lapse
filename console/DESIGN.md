# Lapse console design system: the cyanotype sheet

## The one thing this interface has to do

A permit does not fail loudly, it expires. The failure mode in this domain is silence, so the
console exists to break the silence exactly once per item and then be quiet. It is graded on
whether a contractor standing at a job site can find the single item already costing money in
under five seconds.

The reader runs a small plumbing and heating outfit and holds a phone in one hand.

## The metaphor

The work this product watches is filed on drawings, so the console is a drawing. A cyanotype
sheet: printed grid, ruled trim with station ticks along the top edge, condensed capitals for
titles, dimension lines instead of bar charts, a schedule of quantities instead of KPI tiles,
and a title block at the bottom naming the sheet and where the numbers were read.

Three consoles in this family must never look like one product with three datasets:

| Axis | Lapse | Pullback | Best By |
|---|---|---|---|
| Metaphor | cyanotype drawing sheet | swing tag on the object | stamped case and dual sheets |
| Paper | blueprint blue, dark only | bone, light only | warm carton kraft |
| Type | Barlow Condensed + Barlow + IBM Plex Mono | Archivo + Space Mono | Literata + JetBrains Mono |
| Action | chalk white fill | ink black fill | indigo stamp fill |
| Layout | ruled sheet, dimension lines, boxed details | two-up tag grid | persistent SHELF / KITCHENS split |
| Radius | 0 | 2px | 0 to 1px |

Banned here because a sibling owns them: any serif, Space Mono, JetBrains Mono, a light or bone
paper, a punched-tag card, an indigo or green primary.

## Dark only

A blueprint is a blue print. `color-scheme: dark` is declared and there is no light block. The
ground carries a real drafting grid: 24px minor and 120px major hairlines at 11% and 20%, which
scroll with the page because the page is the sheet.

## Type

| Family | Role |
|---|---|
| Barlow Condensed (500/600/700) | titles and counts, always uppercase |
| Barlow (400/500/600) | prose, decisions, quoted DOB text |
| IBM Plex Mono (400/500) | every measured thing: day counts, dates, job and violation numbers, labels |

The deadline is a measured quantity, so it is set in the mono at up to 44px, and it is the
largest thing on a card. The generic rulebook sentence that repeats on every card of the same
permit type is never larger than the number that differs.

| Token | Spec | Used for |
|---|---|---|
| `--t-statement` | clamp(32px, 2.6vw + 18px, 52px), Barlow Condensed 600 caps | the count of decisions, sheet titles |
| `.record-title` | clamp(22px, 0.9vw + 18px, 28px), condensed caps | what an item is |
| `.anchor` | clamp(30px, 1.8vw + 21px, 44px), Plex Mono 500, tabular | days late or days left |
| `.decision` | clamp(16.5px, 0.4vw + 15px, 18.5px), Barlow | the question that is genuinely a person's |
| `.data` | Plex Mono 12.5px, tabular | checks, quoted DOB text, evidence ids |
| `.label` | Plex Mono 500 10px, 0.16em caps | section labels, class words |
| `.micro` | Plex Mono 11px, tabular | dates, counts, citations |

## Colour

| Role | Value | Meaning |
|---|---|---|
| `--paper` | `#08213A` | the sheet |
| `--sheet` | `#0C2A47` | a panel, the title bar |
| `--sheet-2` | `#103455` | inset, hover |
| `--ink` | `#E9F2F9` | primary text, and the primary button fill |
| `--ink-2` | `#A7C5DC` | secondary prose, citations |
| `--ink-3` | `#7B9EBB` | labels, timestamps |
| `--rule` | `#1D4670` | hairline inside the sheet |
| `--rule-strong` | `#2F5F8E` | trim, station ticks, control borders |
| `--flag` | `#FFC53D` | focus ring, the drafted-response edge, the live mark |
| `--lapsed` | `#FF6F61` | already past its date |
| `--critical` | `#FFA24A` | due inside the week |
| `--due` | `#FFD85E` | due inside the month |
| `--clear` | `#7B9EBB` | no clock on the record |

Chalk white is the only action colour, so the one thing a person can press is the one thing on
the page that is not printed in blue. The deadline ramp is the only warm family on the sheet: a
date is the only thing allowed to glow. Every use of the ramp prints the class word beside it, so
no reading depends on hue.

## Shape and space

4px base, and the page grid is 24px, so vertical rhythm lands on the printed grid where it can.
Container is `max-width: 1120px` inside the trim, `padding-inline: 20px` rising to 32px.
Radius is 0 everywhere. A drawing has no rounded corners.
A detail is a 1px `--rule` box with the deadline class as a 3px left edge. No shadows except the
selection tray, which lifts off the bottom of the sheet.

## Components

### The drawing (the page)

`main.drawing` carries left, right and bottom trim in `--rule-strong` and a 7px strip of station
ticks along the top edge, repeating every 48px.

### Dimension line (what was a stacked bar)

`.dim` is 34px tall between two full-width rules, and each class segment carries its own end tick
above and below the line, so the queue reads as measured to scale rather than as a painted bar.
Every segment is also the control that filters to that class.

### Schedule of quantities

`.qty-row` is `count | class word and worst item`. The count is mono at 26px in the class colour,
right aligned on a 62px column so the digits stack. Pressing a row narrows the list, which is why
the counts are not decoration.

### Detail card

Order is what a person needs, in the order they need it: how long they have, where it is, what it
is, what the engine checked, what it wrote, then the one control. The drafted filing is quoted
whole in `.draft` with a `--flag` left edge, because it is the thing being approved.

### Title block

The provenance line is the drawing's title block: a ruled box, bottom right, with `Read from`,
`Partition`, `Rows` and `Read at`. A number with no origin is a rumour with good posture.

## Motion

One entrance: the report fades up 6px over 380ms. Everything else is 120ms feedback on hover,
press and filter. Reduced motion kills all of it. No pulsing live dot: a still mark is a fact.

## Rules this console holds itself to

- No em dashes anywhere in copy or code.
- Every figure is read from DynamoDB in a server component, or the page says it read nothing.
  An empty queue on a deployment with no key is stated as blank, never as quiet.
- The class word is always printed next to the class colour.
- One control per card, and Approve is visibly off when `LAPSE_AGENT_FUNCTION` is unset, said
  once on the page rather than on every card.
- Empty states say what happened, never "No data".
