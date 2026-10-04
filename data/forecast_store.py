"""Read the Forecast Lab results written offline by scripts/run_forecasts.py. The app only reads
these files; it never fits or trains a model. data/forecasts/ is git-ignored (derived from cached
third-party data; regenerate with the script)."""

import json
import pathlib

import pandas as pd

FORECAST_DIR = pathlib.Path(__file__).resolve().parent / "forecasts"
SCHEMA = 1
SUMMARY = "summary.json"


class ForecastStoreError(RuntimeError):
    pass


def write_summary(summary: dict, frames: dict[str, pd.DataFrame], folder: pathlib.Path | None = None):
    folder = folder or FORECAST_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_csv(folder / f"{name}.csv", index_label="date")
    (folder / SUMMARY).write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")


def load_summary() -> dict:
    path = FORECAST_DIR / SUMMARY
    if not path.exists():
        raise ForecastStoreError("No saved results: run scripts/run_forecasts.py first.")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ForecastStoreError(f"Saved results could not be read ({e}).") from e
    if summary.get("schema") != SCHEMA:
        raise ForecastStoreError("Saved results use an old format: rerun scripts/run_forecasts.py.")
    return summary


def load_frame(name: str) -> pd.DataFrame:
    path = FORECAST_DIR / f"{name}.csv"
    if not path.exists():
        raise ForecastStoreError(f"Missing results file {path.name}: rerun scripts/run_forecasts.py.")
    return pd.read_csv(path, index_col="date", parse_dates=["date"])
