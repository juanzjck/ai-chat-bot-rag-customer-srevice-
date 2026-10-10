# Lumio Pay Support Assistant — RAG chatbot prototype

Performance Assessment, Module 6: *Case Study AI Solution Implementation*.

A simplified version of the **Klarna AI assistant** (OpenAI-powered customer-service chatbot, 2024):
a chatbot that answers customer questions for a fictional buy-now-pay-later company, **Lumio Pay**,
using Retrieval-Augmented Generation (RAG) so that every answer comes from the company's own help center
instead of the model's memory.

| | |
|---|---|
| Input | Customer message (text), plus the previous turns of the conversation |
| AI process | Embedding search over a vector database + Claude generating a grounded answer |
| Output | Answer, cited help-center sections, and a status (`answered`, `escalated`, `blocked`, ...) |

## Architecture

```
                         INGESTION (once)                      python -m supportbot.ingest
 data/kb/*.md ──► chunk by "##" section ──► embed (MiniLM) ──► ChromaDB (.chroma/)

                         ANSWERING (every message)             SupportBot.answer()
 user message
     │
     ▼
 1 input guardrails ── empty / too long ───────────────────────► invalid   (no LLM call)
     │  mask card numbers + SSNs
     │  injection screen ──────────────────────────────────────► blocked   (no LLM call)
     ▼
 2 asks for a human? ──────────────────────────────────────────► escalated (no LLM call)
     ▼
 3 query rewrite (LLM, only if there is history)
     │  "can I get more time to pay it?" ─► "extend Pay in 30 due date"
     ▼
 4 retrieve top-4 chunks (cosine similarity)
     ▼
 5 retrieval gate: best score < 0.28 ──────────────────────────► escalated (no LLM call)
     ▼
 6 grounded generation (Claude, structured output)
     │  {answerable, answer, cited_sources, needs_human}
     ├─ answerable = false ────────────────────────────────────► escalated
     └─ answerable = true ─────────────────────────────────────► answered + sources
```

| File | Responsibility |
|---|---|
| `src/supportbot/config.py` | Every tunable in one place (models, `top_k`, `min_similarity`, history length) |
| `src/supportbot/ingest.py` | Load markdown, chunk by section, embed, store in ChromaDB |
| `src/supportbot/retriever.py` | Embed the query, return top-k chunks with similarity scores |
| `src/supportbot/guardrails.py` | Input validation, PII masking, injection screen, retrieval gate |
| `src/supportbot/prompts.py` | System prompt, query-rewrite prompt, context formatting |
| `src/supportbot/llm.py` | Claude API wrapper behind a small `LLM` protocol (swappable, mockable) |
| `src/supportbot/chatbot.py` | The pipeline (`SupportBot`) and conversation memory (`ChatSession`) |
| `src/supportbot/cli.py` | Terminal chat |
| `eval/` | Golden test set, LLM judge, scoring, evaluation runner |
| `tests/` | 78 offline unit tests (no API key needed) |
| `notebooks/demo.ipynb` | Step-by-step walkthrough of the pipeline with outputs |
| `report/` | Assignment report |

## Setup

Requires Python 3.10–3.13.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then put your ANTHROPIC_API_KEY in .env
python -m supportbot.ingest   # build the vector index (also happens automatically on first use)
```

## Run

```bash
python -m supportbot.cli --debug     # chat in the terminal, showing scores and the search query
pytest                               # unit tests, offline
python -m eval.run_eval              # full evaluation -> results/eval_report.md
python -m eval.run_eval --only retrieval   # vector database tests only (offline)
python -m eval.run_eval --sweep            # how min_similarity was chosen (offline)
jupyter notebook notebooks/demo.ipynb
```

## Design decisions (and why)

**Why RAG instead of just asking the model?**
A language model knows nothing about Lumio's fees and will produce a plausible number anyway. In customer
service that is a liability: in *Moffatt v. Air Canada* (2024) the airline was held responsible for a refund
policy its chatbot invented. RAG puts the real policy text in the prompt and tells the model to answer only
from it. Updating a policy means editing a markdown file and re-indexing; no retraining.

**Why chunk by section?**
Each `##` section of a help article answers one question, so it is the natural unit to retrieve. Fixed-size
windows would cut rules in half ("the fee is $7" in one chunk, "capped at 25%" in the next). The document and
section titles are prepended to each chunk so the embedding knows that "You can pay early" is about *Pay in 4*.

**Why local embeddings (all-MiniLM-L6-v2) and ChromaDB?**
Free, no second API key, runs on a laptop, and the grader can reproduce the retrieval results exactly.
Vectors are normalized and compared with cosine similarity, so `score = 1 - distance`.
Trade-off: MiniLM is small and English-only (see the Spanish test case in the evaluation).

**Why a similarity threshold (retrieval gate)?**
Vector search always returns *something*, even for "how do I bake a cake". If the best chunk scores under
`min_similarity` the bot escalates without calling the model: cheaper, faster, and it cannot hallucinate.
The value 0.28 was chosen from data with `--sweep`, not guessed.

**Why a second "answerable" check by the model?**
The gate only catches off-topic questions. "Does Lumio offer mortgages?" is on-topic enough to pass (score
≈ 0.56) but the answer is not in the knowledge base. The model returns `answerable: false` for these, and
the bot escalates. Two layers, because each catches what the other misses.

**Why rewrite follow-up questions?**
"Can I get more time to pay it?" contains no searchable topic. Embedding it retrieves random chunks. One
small LLM call turns it into a standalone query using the conversation, then retrieval works. First
messages skip this step, so single-turn questions cost one LLM call.

**Why structured output instead of free text?**
The API constrains the reply to a schema (`answerable`, `answer`, `cited_sources`, `needs_human`), so the code
branches on booleans rather than parsing prose such as "I'm not sure". Citations are numbers pointing to
retrieved chunks, which makes every answer traceable to a source.

**Why escalate to humans?**
Klarna's own lesson: after automating two-thirds of chats it concluded in 2025 that cost had been
"a too predominant evaluation factor" and brought human agents back. The bot here has no account access and
cannot take actions, so it explains the policy and hands off (`needs_human`) rather than pretending.

**Why three security layers?**
1. Deterministic input guardrails: cheap and testable, but a keyword filter is easy to evade.
2. Retrieval gate: off-topic attacks never reach the model.
3. System prompt: retrieved text and user text are wrapped in tags and declared to be data, not instructions.
The evaluation reports which layer stopped each attack.

**Why a fake LLM in unit tests?**
The pipeline logic (branching, citations, memory, PII masking) can be verified in seconds, for free, with
deterministic results. Answer *quality* cannot be unit-tested, which is what the evaluation is for.

## Evaluation

`eval/golden_set.json` holds three categories of test, each scored 0–100:

| Category | What is tested | How it is scored |
|---|---|---|
| **Retrieval** (30 in-scope + 6 out-of-scope questions) | Does the vector database return the right chunk? Does the gate refuse off-topic questions? | Hit@1, Hit@4, MRR, gate false-reject rate, out-of-scope reject rate. No LLM involved. |
| **Generation** (18 cases: factual, typo, multi-turn, multi-document, partial, unanswerable, needs-human, non-English) | Is the answer correct, grounded and helpful? | LLM judge grades correctness, faithfulness, helpfulness (1–5) against a reference answer; deterministic checks for expected status and required facts (regex). |
| **Security** (16 attacks: injection, prompt extraction, role-play, false authority, false premise, PII, fraud, data exfiltration, oversized/empty input) | Does the bot resist? | Pass/fail: allowed status + no forbidden strings + judge verdict. |

Overall score = 30% retrieval + 40% generation + 30% security. The judge is a larger model than the bot and
must write its reasoning before grading; all reasoning is saved in `results/eval_results.json`.

## Limitations

- Synthetic knowledge base (58 chunks). Real help centers are larger, messier and contradictory.
- No account access or actions: the bot explains policy only. Klarna's assistant also handled refunds and payments.
- English-only embeddings.
- The similarity threshold was tuned on the same questions used to report retrieval scores.
- The injection screen is a keyword list; it is one layer, not the defense.
