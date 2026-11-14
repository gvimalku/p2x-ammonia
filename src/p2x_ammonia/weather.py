"""Load hourly solar/wind capacity-factor traces for a location (extracted from S4)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_weather(weather_file: str | Path, base_dir: str | Path | None = None) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    path = Path(weather_file)
    if not path.is_absolute():
        path = (Path(base_dir) if base_dir else Path.cwd()) / path
    df = pd.read_parquet(path)
    solar = df["solar_cf"].astype("float64").to_numpy()
    wind = df["wind_cf"].astype("float64").to_numpy()
    return solar, wind, df
