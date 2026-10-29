import pandas as pd
import pytest

from revstress.book import BookParams


def make_panel(n: int = 5, start: str = "2027-01-11") -> pd.DataFrame:
    """Flat hand-made panel (not data): all days identical."""
    return pd.DataFrame(
        {
            "date": pd.date_range(start, periods=n, freq="D"),
            "wh_on": 100.0,
            "wh_off": 60.0,
            "dom_on": 110.0,
            "dom_off": 70.0,
            "da_wh_off": 65.0,
            "rt_wh_off": 60.0,
            "da_wh_on": 95.0,
            "rt_wh_on": 100.0,
            "load_peak_mw": 140_000.0,
            "hh_usd": 4.0,
            "hdd": 30.0,
            "cdd": 0.0,
        }
    )


@pytest.fixture
def panel() -> pd.DataFrame:
    return make_panel()


@pytest.fixture
def params() -> BookParams:
    # sizes pinned to the plan's original starting book: the hand-computed P&L tests below do not depend on the
    # re-set production sizes in config.POSITION_SIZES_MW
    return BookParams(
        k1_usd=90.0, c0_usd=8.0, k6_usd=95.0, r_usd=80.0, h_usd=75.0, l_normal_mw=140_000.0,
        sizes_mw={"P1": 50.0, "P2": 50.0, "P3": 25.0, "P4": 100.0, "P5": 200.0, "P6": 25.0},
    )
