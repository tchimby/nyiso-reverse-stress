# UI (static)

```
python -E -P scripts/export_ui_data.py     # outputs/ -> ui/data/*.json
cd ui && python -m http.server 8000        # open http://localhost:8000
```

Pages: Overview (arms table and caveats), Scenarios (ranked cards: narrative, shock vector, P&L by position and channel, D², q, judge grade), Arms, Factors (daily model), Ablation (severity anchoring), Demo (put `media/demo.mp4`).

The JSON files are the data contract for any other front end: `runs.json`, `scenarios.json`, `factors.json`, `ablations.json`, `meta.json`.
