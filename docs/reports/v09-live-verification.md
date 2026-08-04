# Version 09 Live Verification

Date: 2026-08-05  
Model: `openai/gpt-5.6-luna` through OpenRouter  
Artifact: clean installation of `dist/coding_kid-0.1.0-py3-none-any.whl`  
Total: 51 requests, 117,376 input tokens, 5,411 output tokens, USD 0.011379095

No SWE-bench or batch evaluation was run. The first cancellation attempt is
retained below because it consumed credits even though it did not satisfy the
acceptance condition.

## Parallel research — passed

Two children inspected separate modules. Their monotonic intervals were
216592.273996–216603.219939 and 216592.275315–216606.457734, proving overlap.
The root waited for both and returned the exact constants and function behavior.

| Request | Input | Output | Cost (USD) |
| ---: | ---: | ---: | ---: |
| 1 | 1,325 | 220 | 0.000297550 |
| 2 | 1,772 | 106 | 0.000285025 |
| 3 | 1,031 | 36 | 0.000150400 |
| 4 | 1,031 | 35 | 0.000149800 |
| 5 | 1,102 | 131 | 0.000098055 |
| 6 | 1,104 | 190 | 0.000133705 |
| 7 | 2,306 | 141 | 0.000372775 |
| **Total** | **9,671** | **859** | **0.001487310** |

## Implementation and follow-up — passed

One child implemented `slugify.py` and tests, then completed a second turn via
`followup` on the same ID. The retained record reported `turn_count: 2` and 19
tool calls. The child reported 10 passing tests; an independent clean-environment
run confirmed `10 passed in 0.03s`.

| Requests | Input tokens by request | Output tokens by request | Cost by request (USD) |
| --- | --- | --- | --- |
| 1–7 | 1372, 1725, 1085, 1997, 1277, 2188, 1419 | 193, 137, 81, 93, 64, 38, 104 | .000287225, .000297750, .000184150, .000305350, .000197950, .000296225, .000093190 |
| 8–14 | 1615, 1769, 1945, 2163, 2939, 3112, 3416 | 78, 111, 135, 54, 100, 289, 250 | .000085760, .000102270, .000120960, .000079370, .000178900, .000562325, .000219390 |
| 15–21 | 2307, 3683, 3830, 3903, 4049, 2565, 2788 | 51, 74, 19, 75, 121, 125, 123 | .000067625, .000112205, .000490075, .000092695, .000578650, .000395550, .000422225 |
| 22–28 | 2993, 4225, 4735, 5131, 5214, 3269, 3491 | 47, 223, 380, 29, 143, 126, 92 | .000402250, .000537420, .000334270, .000114520, .000147755, .000163875, .000491500 |
| **Total** | **80,205** | **3,355** | **0.007361430** |

## Cancellation attempt with a short delay — not accepted

The model initially violated the conditional action contract by supplying a
message to `wait` and `stop`. Both calls returned explicit validation errors and
the model recovered, but the 20-second command completed naturally during that
recovery. The record was `completed` and the late marker existed, so this attempt
was not counted as a pass.

| Request | Input | Output | Cost (USD) |
| ---: | ---: | ---: | ---: |
| 1 | 1,373 | 158 | 0.000266350 |
| 2 | 1,667 | 47 | 0.000236500 |
| 3 | 1,033 | 100 | 0.000189050 |
| 4 | 1,735 | 50 | 0.000055440 |
| 5 | 1,867 | 73 | 0.000077920 |
| 6 | 2,022 | 69 | 0.000079715 |
| 7 | 1,175 | 20 | 0.000040350 |
| 8 | 2,112 | 47 | 0.000059940 |
| 9 | 2,266 | 48 | 0.000311975 |
| 10 | 2,421 | 164 | 0.000140705 |
| **Total** | **17,671** | **776** | **0.001457945** |

## Cancellation and cleanup with a 120-second delay — passed

The root waited two seconds, observed `last_activity: execute`, stopped the
child, and polled `stopped`. The result retained `ready evidence`, exit code 125,
and `cancelled: true`. The ready marker existed, the late marker did not, no
worker thread survived shutdown, persistent-session replay succeeded, and the
old process-local Agent ID returned `Unknown or expired child Agent`.

| Request | Input | Output | Cost (USD) |
| ---: | ---: | ---: | ---: |
| 1 | 1,372 | 117 | 0.000241625 |
| 2 | 1,034 | 77 | 0.000175375 |
| 3 | 1,623 | 51 | 0.000233400 |
| 4 | 1,755 | 53 | 0.000064800 |
| 5 | 1,934 | 51 | 0.000272275 |
| 6 | 2,111 | 72 | 0.000084935 |
| **Total** | **9,829** | **421** | **0.001072410** |
