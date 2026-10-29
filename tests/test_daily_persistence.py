"""Persistence tail of the daily model: after a shock ends its price-level and spread effects decay as phi^k."""
import warnings

import numpy as np

from revstress import config
from revstress.shock import PassThrough, apply_shock
from revstress.synthetic import generate_synthetic_panel


def base():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return generate_synthetic_panel(seed=1, start="2021-01-01", end="2021-01-12", warn=False).head(10)


def shock(**kw):
    return {**config.NEUTRAL_SHOCK, "duration_days": 3, "gas_hh_pct": 30.0, "dom_minus_wh_usd": 40.0, **kw}


def test_no_persistence_snaps_back():
    b = base()
    out = apply_shock(b, shock(), 0, PassThrough(l_normal_mw=float(b.load_peak_mw.median())))
    assert np.allclose(out.loc[3:, "rt_wh_on"], b.loc[3:, "rt_wh_on"]) and np.allclose(out.loc[3:, "dom_on"], b.loc[3:, "dom_on"])


def test_tail_decays_geometrically_and_leaves_other_days_alone():
    b = base()
    pt = PassThrough(l_normal_mw=float(b.load_peak_mw.median()), phi_level=0.5, phi_spread=0.5)
    out = apply_shock(b, shock(), 0, pt)
    step = (out.rt_wh_on / b.rt_wh_on).to_numpy()
    assert step[2] > 1.0  # last shocked day is up
    assert np.isclose(np.log(step[3]) / np.log(step[2]), 0.5) and np.isclose(np.log(step[4]) / np.log(step[2]), 0.25)
    spread = ((out.dom_on - out.rt_wh_on) - (b.dom_on - b.wh_on)).to_numpy()
    assert np.isclose(spread[2], 40.0) and np.isclose(spread[3], 20.0) and np.isclose(spread[4], 10.0)
    assert not out.loc[3:, "shock_day"].any() and np.isclose(out.loc[9, "rt_wh_on"], b.loc[9, "rt_wh_on"], rtol=0.01)
    assert (out.load_peak_mw.to_numpy() == b.load_peak_mw.to_numpy()).all()  # load and gas inputs are not carried into the tail
