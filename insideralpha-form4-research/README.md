# InsiderAlpha Form 4 Research

Reproducible research materials for InsiderAlpha studies built from SEC Form 4
ownership filings.

The first package accompanies:

> A $1M Insider Buy Is Not Always Large: Measuring Purchases Against Existing
> Holdings

Report: https://insider-alpha.com/blog/2026-08-04-insider-purchase-size-relative-to-holdings

## What is public

- A bundled 10,000-row, 64-column sample of the versioned Form 4 release.
- The complete filtering, event construction and summary code.
- A notebook that downloads the sample and runs the methodology.
- Machine-readable copies of the statistics published in the report.

The sample is selected at deterministic, evenly spaced release positions. It
is useful for inspecting the schema and executing the workflow, but it is not
the full study population. Exact report figures require the complete release.
The notebook labels sample output accordingly.

## Run the notebook

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/relative-purchase-size.ipynb
```

The notebook verifies and loads the bundled sample automatically, so its
default workflow does not require network access. To analyze a local full
release, set `INSIDERALPHA_DATASET_PATH` before starting Jupyter:

```bash
export INSIDERALPHA_DATASET_PATH=/absolute/path/to/insideralpha-form4-release.csv
jupyter lab notebooks/relative-purchase-size.ipynb
```

The analysis can also run without Jupyter:

```bash
python analysis/relative_purchase_size.py /path/to/dataset.csv --output-dir output
```

Input may be a CSV file or a ZIP archive containing one CSV file.

## Reproducibility contract

The implementation follows the report's published unit of analysis:

1. Keep current, non-derivative code `P` transactions dated on or after
   2007-01-01.
2. Require direct ownership, positive purchased shares, positive reported
   post-transaction holdings and calculated 30-, 90- and 180-day outcomes.
3. Aggregate price tranches to one ticker-owner-date-security-ownership event.
4. Calculate purchased shares divided by shares owned after the event.
5. Exclude calculated fractions above 100%.
6. Summarize the predefined holdings-relative buckets and matched-issuer
   diagnostics.

Legacy rows without canonical transaction-table or holdings fields are
excluded intentionally. See the report for interpretation and limitations.

## Licenses

- Analysis code and notebook: MIT, see `LICENSE-CODE`.
- Public 10,000-row sample: CC BY 4.0, see `LICENSE-DATA.md`.
- Full dataset: not included and not covered by the sample license.

## Citation

Use `CITATION.cff` or `CITATION.bib`. The repository metadata identifies Daniel
Antonio Melgar Mendez and InsiderAlpha Research as the responsible author and
research organization.
