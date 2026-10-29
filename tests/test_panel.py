import warnings

import numpy as np
import pandas as pd
import pytest

from revstress import config
from revstress.panel import PANEL_COLUMNS, PanelError, panel_window, validate_panel
from revstress.synthetic import SYNTHETIC_WARNING, generate_synthetic_panel
from conftest import make_panel


def test_valid_panel_passes():
    assert validate_panel(make_panel(), fallback=False) is not None


def test_missing_column_raises():
    with pytest.raises(PanelError, match="missing"):
        validate_panel(make_panel().drop(columns="dom_on"), fallback=False)


def test_nan_raises():
    df = make_panel()
    df.loc[2, "hh_usd"] = np.nan
    with pytest.raises(PanelError, match="NaN"):
        validate_panel(df, fallback=False)


def test_non_monotone_and_duplicate_dates_raise():
    df = make_panel()
    df.loc[3, "date"] = df.loc[1, "date"]
    with pytest.raises(PanelError, match="increasing"):
        validate_panel(df, fallback=False)
    df = make_panel()
    df.loc[3, "date"] = df.loc[2, "date"]
    with pytest.raises(PanelError, match="increasing"):
        validate_panel(df, fallback=False)


def test_settlement_consistency_check():
    df = make_panel()
    df.loc[0, "wh_on"] = 101.0
    with pytest.raises(PanelError, match="settlement"):
        validate_panel(df, fallback=False)
    validate_panel(df, fallback=False, check_settlement=False)


def test_fallback_needs_only_three_columns(monkeypatch):
    df = make_panel()[["date", "wh_on", "hh_usd"]]
    validate_panel(df, fallback=True)
    with pytest.raises(PanelError):
        validate_panel(df, fallback=False)
    monkeypatch.setattr(config, "FALLBACK_BOOK", True)
    validate_panel(df)


def test_synthetic_panel_valid_labelled_deterministic():
    with pytest.warns(UserWarning, match="SYNTHETIC"):
        a = generate_synthetic_panel(1, "2022-01-01", "2023-12-31")
    b = generate_synthetic_panel(1, "2022-01-01", "2023-12-31", warn=False)
    c = generate_synthetic_panel(2, "2022-01-01", "2023-12-31", warn=False)
    validate_panel(a, fallback=False)
    assert a.equals(b) and not a.equals(c)
    assert (a["synthetic_source"] == "SYNTHETIC").all() and a.attrs["warning"] == SYNTHETIC_WARNING
    assert list(a.columns[: len(PANEL_COLUMNS)]) == list(PANEL_COLUMNS)
    assert a["wh_on"].max() <= config.ENERGY_COMPONENT_CAP_USD
    assert a["wh_on"].mean() > a["wh_off"].mean()
    assert (a["dom_on"] - a["wh_on"]).mean() > 0


def test_synthetic_gas_price_link():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = generate_synthetic_panel(3, "2019-01-01", "2025-12-31")
    assert np.corrcoef(np.log(a["hh_usd"]), np.log(a["wh_on"]))[0, 1] > 0.3


def test_panel_window():
    w = panel_window(make_panel(10), "2027-01-13", 4)
    assert len(w) == 4 and w["date"].iloc[0] == pd.Timestamp("2027-01-13")
    with pytest.raises(PanelError):
        panel_window(make_panel(10), "2027-01-13", 40)
