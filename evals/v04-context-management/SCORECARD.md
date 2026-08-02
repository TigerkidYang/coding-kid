# Version 04 Context-Management Scorecard

- Model: `openai/gpt-5.6-luna`
- Paid requests: **30 / 30**
- Version 03 outcome: **3/3**
- Version 04 process: **3/3**
- Version 04 outcome: **3/3**
- Initial Version 04 CLI compaction: **pass**
- Initial Version 04 CLI outcome: **fail** (repeated completed reads until cap)
- Post-fix CLI retry: **pass**, process and outcome, **6 / 60** requests

| Fixture | V03 outcome | V04 process | V04 outcome | Compactions |
| --- | --- | --- | --- | ---: |
| intent-correction | pass | pass | pass | 1 |
| tool-evidence | pass | pass | pass | 1 |
| repeated-compaction | pass | pass | pass | 2 |

The initial bounded batch exposed a continuation-loop defect. After the handoff
contract was corrected, the isolated CLI retry compacted once, reused the
recorded evidence, wrote and verified `result.txt`, and finished successfully.

Completion target met: V04 process and outcome 3/3, V04 outcome not below V03,
and the corrected real CLI flow passes within its authorized request cap.
