# Coding Kid V01 Baseline — Task Decomposition Eval Slice

Date: 2026-07-25  
Agent: Coding Kid Version 01 (`openai/gpt-5.6-luna`)  
Purpose: Find tasks that V01 fails, so Version 02 (Todo) can be measured against them.

## Method notes

1. **Do not trust AgentBench prompts that already list steps 1–5.**  
   That leaks task decomposition into the user message. Round 1 used those prompts and V01 passed multi-step tasks. Round 2 used **goal-only** prompts from the same fixtures.

2. **Verify with isolated pytest** (venv python, cwd = workspace). Early harness bugs falsely reported PASS by collecting Coding Kid’s own 42 tests.

3. **SWE-bench Lite** instance `pylint-dev__pylint-6506` was run as a real checkout at `base_commit` with official `test_patch` applied first (standard SWE-bench protocol).

## Results

| Task | Source | Prompt style | V01 Outcome | Why it failed / passed |
|------|--------|--------------|-------------|------------------------|
| code-001 | AgentBench-Live | goal-only | **PASS** | Single-file off-by-one; read→patch→pytest. Too easy for Todo eval. |
| multi-001 | AgentBench-Live | numbered steps (round1) | PASS | Steps were given in the prompt. |
| multi-001 | AgentBench-Live | **goal-only** | **FAIL** | Identified 3 bugs, hit 12-tool budget before any patch/CHANGELOG. |
| multi-002 | AgentBench-Live | numbered steps (round1) | PASS | Steps were given in the prompt. |
| multi-002 | AgentBench-Live | **goal-only** | **FAIL** | Wrote `remote.py` only; no tests/README; budget exhausted. |
| pylint-6506 | SWE-bench Lite | issue text | **FAIL** | Explored 12 tools (read/search only); no edit; suggested wrong file. |

### Headline

```text
Useful for V02 Todo eval (V01 fails):  3
Too easy / contaminated by step list:  code-001; multi-* with numbered prompts
```

V01 on the **fair** multi-step / SWE slice: **0 / 3** outcome passes.

## Keep for Version 02 comparison

1. `agentbench multi-001` — goal-only prompt (fix 3 bugs + CHANGELOG)  
2. `agentbench multi-002` — goal-only prompt (remote config + tests + docs)  
3. `SWE-bench Lite pylint-dev__pylint-6506` — real issue + fail-to-pass tests  

Optional later (same protocol, not yet run on V01): other Lite ids that need reproduce→locate→edit→verify without a pre-written checklist in the prompt.

## Do not use for Todo proof

- AgentBench tasks **with numbered workflow already in the prompt**  
- Single-bug `code-001` (V01 already solves it)

## Hypothesis for Version 02

Todo should help V01’s failure mode: **budget burned on exploration before edits**.  
A checklist that forces “fix A → fix B → fix C → verify → changelog” may raise outcome on multi-001/002.  
SWE-bench pylint may still need better search/navigation; treat Process (todo used + followed) separately from Outcome if patch still fails.

## Artifacts

- `v1_baseline_report.json` — round 1 (contaminated prompts; harness bugs)  
- `v1_baseline_round2_report.json` — goal-only AgentBench  
- `v1_swe_pylint_6506_report.json` — SWE-bench Lite instance  
- Workspaces under `workspaces/` and `swe-pylint-full/`
