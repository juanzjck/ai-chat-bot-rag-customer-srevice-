# <Topic name, e.g. "Pay in 4">

TEMPLATE NOTES - everything between the "# " title and the first "## " heading
is ignored by the ingester, so these notes are safe to leave in or delete.

How to use
1. Copy this file to data/kb/<topic-in-kebab-case>.md (the file name is the
   citation source and the chunk id prefix, so keep it short and stable).
2. Replace the title and the sections below.
3. Rebuild the index: python -m supportbot.ingest

Rules the chunker applies
- Exactly one "# " title per file. It is prepended to every chunk.
- Each "## " section becomes one chunk. One section = one customer question.
- A section with no body is skipped.
- A body over 900 characters is split on blank lines, so keep each paragraph
  able to stand on its own. Do not put a blank line in the middle of one rule.
- "### " subheadings and lists stay inside their "## " chunk.
- Do not write "## " at the start of a line unless you mean a new section.

Writing for retrieval
- Name the topic in the heading: "Eligibility for Pay in 4", not "Eligibility".
- Name the topic in the body too; avoid "it" / "this plan" as the only subject.
- State exact numbers, limits, deadlines and fees. No "see above".
- Use the words a customer would type ("late fee", "refund", "change due date").
- One fact lives in one section. Do not repeat a rule across files.

## How <topic> works
<2-4 sentences: what it is, who it is for, the key numbers.>

## Eligibility for <topic>
<Requirements as full sentences: age, country, order min/max, credit check.>

## <Topic> fees and limits
<Exact amounts, caps, when they apply, when they do not.>

## How to <do the main task> with <topic>
<Steps in the app: where to tap, what the customer sees, how long it takes.>

## <Topic> deadlines and timing
<Days/hours for each step, counted from which event.>

## What happens if <common problem> with <topic>
<Consequence, what the customer can do, when to contact support.>
