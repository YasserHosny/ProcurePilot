# Product Matching Evaluation

`run_eval.py` reports precision at auto-accept, recall, review-band size, alias hit rate and ECE.
Until `ml/benchmarks/product_matching/heldout.jsonl` contains a real 500+ item held-out labelled
set with hard negatives, the quality gates are reported as unvalidated.
