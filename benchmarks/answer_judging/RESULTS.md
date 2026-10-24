# Answer-judging experiment — October 23, 2026

**Recommendation: the existing Qwen2.5-7B with binary-only output is the strongest tested candidate. Do not rely on the current fast checks.** Neither of the tested compact decision models matched its accuracy. These measurements preceded the production change. JParty now defaults to the binary local judge with exact-match-only fast acceptance; the tables below retain the original pipeline results for comparison.

## What actually ran

- Four candidates, two input modes, **920 core response cases from one sampled text-only clue in each of 100 complete archived games**. This is not every clue from those games.
- 80 development games and 20 held-out games. 910 core cases are scored; ten ambiguous partial answers remain excluded.
- An additional **52 reviewed semantic challenges** from the same game corpus: aliases, chemical names/formulas, similar names, incorrect dates/titles, and context traps. These are an exploratory stress test, not a new independent holdout.
- **7,776 distinct model judgments** across the two suites, with no unresolved request/parse errors in the final results. Interrupted/retried attempts remain in the raw logs; summaries keep the latest attempt per case/context.
- All player responses are constructed test cases attached to real archived clues, **not real contestant transcripts**. Partial and semantic labels are provisional assistant adjudication, not independently verified human labels. The official response supplies the reference.

## Production-style full input: model alone

Each model receives clue text, reference answer, and player response. Category is absent, matching the current production request; category-sensitive clues are therefore a known limitation.

| Candidate | Accuracy | Wrong accepted / 578 | Correct rejected / 332 | Median | 95th percentile |
|---|---|---|---|---|---|
| Kev-0.8B | 65.9% | 255/578 | 55/332 | 44 ms | 52 ms |
| Qwen2.5-7B · binary | 98.2% | 7/578 | 9/332 | 244 ms | 387 ms |
| Qwen2.5-0.5B · binary | 63.5% | 0/578 | 332/332 | 69 ms | 147 ms |
| GLiNER2.5-Decide · CPU | 67.1% | 0/578 | 299/332 | 173 ms | 256 ms |

A model that rejects everything scores **63.5%** on this deliberately negative-heavy core set. Low false acceptance does not make a candidate usable if it rejects most valid answers. The tiny Qwen candidate and GLiNER suffer from that problem.

HTTP candidates were measured on the same 16 GB Apple Silicon Mac with caches enabled. GLiNER uses four CPU threads and in-process calls, while Kev uses MLX and Qwen uses Ollama. Some runs overlapped or had other models resident, so these are observed local latencies, not isolated throughput, cold-start, or memory benchmarks. Pipeline replay has no independently measured latency.

## Held-out games, full input

These 182 scored cases come from the twenty reserved games. Repeated variants of a clue are correlated; the effective number of independent examples is much smaller than the case count. Public archived clues may also have appeared in model pretraining. Holding games out here does not establish training-data exclusion.

| Candidate | Accuracy | Wrong accepted / 114 | Correct rejected / 68 |
|---|---|---|---|
| Kev-0.8B | 65.4% | 52/114 | 11/68 |
| Qwen2.5-7B · binary | 98.4% | 1/114 | 2/68 |
| Qwen2.5-0.5B · binary | 62.6% | 0/114 | 68/68 |
| GLiNER2.5-Decide · CPU | 65.9% | 0/114 | 62/68 |

## Reduced context

The reduced mode keeps only reference answer and player response. It does not truncate the player's answer; incomplete player responses are a separate case type.

| Candidate | Clue + reference + response | Reference + response only |
|---|---|---|
| Kev-0.8B | 65.9% | 86.4% |
| Qwen2.5-7B · binary | 98.2% | 89.0% |
| Qwen2.5-0.5B · binary | 63.5% | 63.5% |
| GLiNER2.5-Decide · CPU | 67.1% | 71.2% |

Reducing context helps Kev on this screen, but does not make it reliable. It hurts the stronger Qwen judge, especially on valid question-form and partial responses. This is evidence against choosing a single input layout purely for speed.

## Additional semantic challenges

| Candidate | Accuracy | Wrong accepted / 32 | Correct rejected / 20 |
|---|---|---|---|
| Kev-0.8B | 67.3% | 17/32 | 0/20 |
| Qwen2.5-7B · binary | 96.2% | 1/32 | 1/20 |
| Qwen2.5-0.5B · binary | 61.5% | 0/32 | 20/20 |
| GLiNER2.5-Decide · CPU | 59.6% | 1/32 | 20/20 |

Even the leading Qwen judge is fallible: it accepted reversed name order, **Stuart Gilbert**, for painter **Gilbert Stuart**, and rejected **sodium chloride** for a clue whose reference is **salt**. Those labels should receive human review alongside the rest of the benchmark before deployment.

## The fast-check problem

| Candidate | Model alone | Current pipeline replay | Exact-only replay, proposed |
|---|---|---|---|
| Kev-0.8B | 65.9% | 71.5% | 77.3% |
| Qwen2.5-7B · binary | 98.2% | 88.2% | 98.9% |
| Qwen2.5-0.5B · binary | 63.5% | 86.4% | 97.0% |
| GLiNER2.5-Decide · CPU | 67.1% | 86.4% | 97.0% |

The current substring acceptance rule accepts a reference inside a denial, such as **not Paris**, before any model sees it. In this corpus the current pipeline accepts **97 of the 100 explicit negations**, regardless of which model is selected. The low-overlap rejection rule also rejects valid **H2O ↔ water** aliases. A name contained in a different referent, such as the **planet Jupiter** when the clue asks for the Roman deity, can pass the substring rule.

The proposed exact-only replay retains the empty-response rejection and normalized exact matches, then defers everything else to the model. It is a counterfactual evaluation only; it has **not** replaced the game's heuristics. Its higher score does not prove those checks are safe on every possible input.

The tiny model's 97% exact-only replay score is especially misleading: exact checks handle most constructed positive cases, while the model simply rejects everything else. It still rejects all twenty valid aliases in the semantic challenge. It is not a suitable substitute for the larger judge on that evidence.

## Why the current LLM feels slow

The current JSON judge was profiled on 31 matching core cases, before stopping that expensive pilot. Its median was **2.11 seconds**, versus **0.25 seconds** for the same cases in binary-only mode. The binary experiment caps generation at two tokens and accepts `true` or `false` with optional final punctuation. It does not ask for a reason or self-reported confidence.

This is a small, non-randomized timing pilot, not an accuracy comparison of the full JSON judge. The full 100-game sampled comparison used binary output for Qwen.

## Next implementation supported by this evidence

1. Keep Qwen2.5-7B for generation and test a separate binary-only answer-judging path that reuses those weights.
2. Tighten the fast checks: keep empty/exact matches, remove unconditional substring acceptance, and stop rejecting semantic aliases just because they share few letters.
3. Keep a review/fallback path for uncertain answers. A two-token boolean has no calibrated confidence score; do not invent one.
4. Validate against more clues per game, independent human labels, real transcripts, and a fresh game holdout before claiming production accuracy. Test category inclusion explicitly.

Larger Kev checkpoints and fine-tuned domain classifiers were not tested. A newer Qwen3.5-0.8B could not be pulled because the installed Ollama runtime does not support its manifest; the runtime was not upgraded. A compatible Qwen2.5-0.5B was tested instead. The new small model and optional GLiNER environment were installed only for the experiment; the active game configuration was left alone.

## Reproduce and inspect

See [benchmark methods and commands](README.md). The deterministic corpus manifest and per-request JSONL records are in the ignored `cache/` and `runs/` directories. [Structured result summary](results-summary.json), [partial-answer adjudications](reviewed_labels.json), and [semantic challenge definitions](semantic_challenges.json) are retained alongside this report.

Dataset source: [public Jeopardy archive mirror](https://github.com/ryanwholey/jeopardy_bot/blob/master/JEOPARDY_QUESTIONS1.json). Alternative classifier: [GLiNER2.5-Decide model card](https://huggingface.co/fastino/GLiNER2.5-Decide).
