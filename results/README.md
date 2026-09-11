# Benchmark results

All conversion outputs, downloaded releases, and generated evaluation reports live
under `runs/`, which is ignored by Git. Use a separate directory for each experiment.

```bash
uv run pdf-benchmark convert reducto --output-dir results/runs/reducto
uv run pdf-benchmark evaluate \
  --markdown-source reducto=results/runs/reducto/markdowns \
  --output-dir results/runs/evaluation
```

To inspect a published run, select its release and destination explicitly:

```bash
uv run pdf-benchmark results download --release all-tools-2026-09-10 \
  --directory results/runs/published-september
```

Evaluation writes `scores.csv`, `scores_by_category.csv`, `granular.csv`,
`filtered.csv`, and `ground_truth.json`. Reference snippets are maintained in
`data/ground_truth/references.json`.
