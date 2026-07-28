# Version 02 Task-Decomposition Evaluation Protocol

## Question

Does the Version 02 session-scoped `todo` tool help Coding Kid complete
multi-step SWE-bench Verified tasks more reliably than Version 01?

This is a feature-specific paired evaluation, not a replacement for the full
SWE-bench Verified leaderboard.

## Non-negotiable controls

- Use official `SWE-bench/SWE-bench_Verified` instances.
- Grade generated patches with the official SWE-bench Docker harness.
- Pull all instance images through an explicitly named domestic registry.
- Retag the domestic image to the exact official image name and verify that the
  two local tags have the same Docker image ID.
- Abort before the harness if any required official image is absent locally.
  The harness must never be allowed to fall back to Docker Hub.
- Run Version 01 and Version 02 with the same model, problem statement, tool
  budget, time limit, repository state, and Docker test environment.
- Do not expose the gold patch or official test patch to either agent.
- Preserve every generated patch, tool trace, final answer, and harness report.

## Calibration and final set

Task selection has two phases.

### Calibration phase

Use a disposable candidate set to find the difficulty and task structure that
can reveal a task-decomposition effect. Candidate tasks should:

- require changes in at least two source locations according to the hidden gold
  patch;
- have a moderate public solve frequency rather than being trivial or nearly
  impossible;
- have bounded patch and test size;
- describe more than one behavioral requirement or require investigation,
  implementation, and verification across related code paths.

Calibration results may change the selection rule. They are not the final
reported score.

### Frozen final phase

After calibration, select ten previously unused instances using the frozen
selection rule. Do not replace an instance after seeing Version 02's result.

The final set is directional evidence for this teaching project. With only ten
instances it is not presented as a statistically representative estimate of
full SWE-bench performance.

## Primary and secondary evidence

Primary outcome:

- official harness `resolved` result for each paired instance.

Clear Version 02 progress requires:

- at least three more resolved instances than Version 01;
- at least three Version-02-only paired wins;
- no more than one Version-01-only regression.

Qualitative task-decomposition evidence requires at least two Version-02-only
wins whose traces show that the todo checklist:

- represented distinct investigation, implementation, or verification steps;
- was updated as work progressed;
- retained or recovered a required step that Version 01 omitted or abandoned.

Process metrics such as todo-call count are supporting evidence only. Calling
`todo` without improving the official outcome does not count as progress.

