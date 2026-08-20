# Quotation Extraction Evals

`run_eval.py` reports field-level accuracy, document exact match, arithmetic-validation pass rate,
cost per document, and Expected Calibration Error (ECE).

Until the extraction provider is switched away from `stub` and a real held-out benchmark is present,
the harness can prove only that metrics are computed and reported. It cannot honestly validate the
90% extraction accuracy gate or the 5% calibration gate.
