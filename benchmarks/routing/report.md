# E04 candidate-routing benchmark report

Generated: 2026-07-15T19:11:28+00:00

| metric | value |
|---|---|
| corpus size | 9 |
| candidate-hit rate | 88.89% |
| false-accept rate | 0.00% (0) |
| false-reject rate | 0.00% (0) |
| latency p50 (ms) | 2.316 |
| latency p95 (ms) | 2.912 |
| net cost savings vs full analysis | 18.89% |

| item | expect fast_path | candidate hit | routed_to | verification | latency (ms) |
|---|---|---|---|---|---|
| nv_invoice_20260042 | True | True | fast_path | accepted | 3.164 |
| nv_invoice_20260043 | True | True | fast_path | accepted | 2.254 |
| mbr_report_001 | False | False | full_analysis | None | 1.068 |
| decoy_nv20260042_rot1 | False | True | full_analysis | rejected | 2.316 |
| decoy_nv20260042_rot2 | False | True | full_analysis | rejected | 2.383 |
| decoy_nv20260042_rot3 | False | True | full_analysis | rejected | 2.312 |
| decoy_nv20260043_rot1 | False | True | full_analysis | rejected | 2.345 |
| decoy_nv20260043_rot2 | False | True | full_analysis | rejected | 2.534 |
| decoy_nv20260043_rot3 | False | True | full_analysis | rejected | 2.267 |
