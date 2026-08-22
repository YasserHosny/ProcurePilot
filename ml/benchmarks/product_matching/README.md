# Product Matching Benchmark

Versioned held-out product matching data belongs here.

Expected file for the harness:

```text
ml/benchmarks/product_matching/heldout.jsonl
```

Each JSONL record should include a line, ranked candidates with confidence and routing metadata,
and the labelled expected workspace product. The real gate requires 500+ labelled pairs including
hard negatives; no such benchmark is committed yet.
