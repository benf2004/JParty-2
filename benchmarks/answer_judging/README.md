# Text-only answer-judging benchmark

This evaluates judgement, not speech recognition, game control, or text-to-speech. It leaves JParty settings and production heuristics unchanged.

## Corpus and labels

The source is the public [216,930-clue Jeopardy archive mirror](https://github.com/ryanwholey/jeopardy_bot/blob/master/JEOPARDY_QUESTIONS1.json). The downloaded JSON, selected-game manifest, and outputs stay in ignored `cache/` and `runs/` directories. Source and manifest hashes are recorded. The source is third-party archived content, not a new freely licensed dataset produced by this project.

The initial screen samples **one text-only clue from each of 100 complete archived games**, not all 6,100 clues. The deterministic seed is 23010. Eighty games are development and twenty are held out. Increasing `--clues-per-game` expands the corpus without reusing a game across splits. Media-dependent clues with links or recognizable visual references are excluded; this filter cannot guarantee every remaining clue is self-contained.

Each clue has generated responses: the official answer, question form, capitalization variant, a punctuation placeholder, a spoken placeholder, an explicit non-answer, an empty answer, and a negation of the official answer. Multiword answers also have first-word and last-word fragments.

These are **generated test responses attached to real clues, not real contestant transcripts**. The reference answer and unambiguous transformations establish the simple labels. Partial answers receive separate provisional semantic review in `reviewed_labels.json`, including surnames, established aliases, and information already supplied by the clue/category. Debatable cases remain unscored. Labels were assigned before inspecting model predictions. This is assistant review, not independent human adjudication; review the labels before making a production decision.

## Comparisons

- `full`: the current production Kev input: clue text, expected answer, and player answer. **Category is currently absent from production.** Some short clues therefore lose essential context.
- `answer_only`: expected answer and player answer, with clue text omitted.
- Model-only: always requests a decision, even for an empty response, to expose model behavior.
- Pipeline replay: existing empty-answer and fast checks override model decisions exactly where production skips the model. API failures remain errors, not silent fallbacks or correct rejections.
- Exact-only replay: a proposed alternative that retains empty/exact checks and defers everything else to the model. This is evaluated only; production fast checks are unchanged.
- `kev`: the current yes/no probability API, using the production instruction and threshold of 0.5.
- `local`: the existing LLM JSON judgement prompt, including confidence and a short reason.
- `local_boolean`: the same decision task with a two-token true/false response, an experiment to avoid JSON/reason generation overhead. It is not the current production LLM prompt.
- `gliner`: GLiNER2.5-Decide via its native classification interface, on CPU with four threads. This is an additional candidate, not a provider added to the game.

Latency is sequential, end-to-end local HTTP wall time for Kev/Ollama, or in-process inference time for GLiNER. Prefix caches remain enabled, initial requests are retained, and the desktop's other local services may stay resident. Pipeline replay has no independently measured latency. Do not treat the results as cold-start, isolated-memory, or cross-hardware benchmarks. Small pilot runs are clearly separate from complete runs.

Report false accepts and false rejects separately, by response type and split. A rejection-only model has a high baseline on this deliberately negative-heavy stress test. Overall accuracy alone is inadequate. Repeated variants of one clue are correlated; do not interpret each variant as an independent real-world observation. Never tune a threshold on the held-out results or describe this preliminary screen as proof of production accuracy.

The additional semantic suite is defined in `semantic_challenges.json` and generated from the same hundred-game corpus. It adds reviewed aliases and near misses, including chemical formulas and cases where a repeated acronym or an identical name is insufficient in context. It is exploratory, not a new independent holdout:

```bash
.venv/bin/python scripts/benchmark_answer_judging.py prepare-challenges \
  --manifest benchmarks/answer_judging/cache/semantic-manifest.json
.venv/bin/python scripts/benchmark_answer_judging.py run \
  --manifest benchmarks/answer_judging/cache/semantic-manifest.json \
  --backend kev --output benchmarks/answer_judging/runs/kev-0.8b-semantic.jsonl
```

## Run

From the project root, with the corresponding local server running:

```bash
.venv/bin/python scripts/benchmark_answer_judging.py prepare
.venv/bin/python scripts/benchmark_answer_judging.py run \
  --backend kev --base-url http://localhost:8009/v1 --model kev-latest \
  --output benchmarks/answer_judging/runs/kev-0.8b.jsonl
.venv/bin/python scripts/benchmark_answer_judging.py run \
  --backend local_boolean --base-url http://localhost:11434/v1 --model qwen2.5:7b \
  --output benchmarks/answer_judging/runs/qwen2.5-7b-boolean.jsonl
```

Runs append each result immediately and resume unfinished requests. An output cannot be reused for another model or manifest. Use distinct output filenames for different Kev checkpoints even though the server API calls each checkpoint `kev-latest`. Partial labels are applied during summarization rather than changing the model inputs or invalidating resumability.

```bash
.venv/bin/python scripts/benchmark_answer_judging.py summarize \
  --output benchmarks/answer_judging/runs/kev-0.8b.jsonl
```

The GLiNER candidate uses a separate optional Python environment, not JParty's dependencies:

```bash
uv venv --python 3.13 benchmarks/answer_judging/cache/gliner-env
uv pip install --python benchmarks/answer_judging/cache/gliner-env/bin/python 'gliner2[local]'
benchmarks/answer_judging/cache/gliner-env/bin/python scripts/benchmark_answer_judging.py run \
  --backend gliner --model fastino/GLiNER2.5-Decide \
  --output benchmarks/answer_judging/runs/gliner2.5-decide.jsonl
```
