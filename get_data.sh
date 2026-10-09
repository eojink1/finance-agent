#!/bin/sh
# Downloads DABstep data, tasks and the official scorer into data/ (gitignored).
set -e
cd "$(dirname "$0")"
B=https://huggingface.co/datasets/adyen/DABstep/resolve/main/data
mkdir -p data/context data/tasks
for f in acquirer_countries.csv fees.json manual.md merchant_category_codes.csv merchant_data.json payments-readme.md payments.csv; do
  curl -sfL "$B/context/$f" -o "data/context/$f"
done
for f in dev.jsonl all.jsonl; do
  curl -sfL "$B/tasks/$f" -o "data/tasks/$f"
done
curl -sfL https://huggingface.co/spaces/adyen/DABstep/raw/main/dabstep_benchmark/evaluation/scorer.py -o data/scorer.py
wc -l data/tasks/*.jsonl
