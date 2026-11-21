"""Shared ETF duration calculation, bound by the framework runner."""

import numpy as np
import pandas as pd

DAYS = 60


def inputs(ticker):
    # There is no scenario axis or app filter associated with this method.
    return {"fit": fit, "fund_channel": fund_channel, "fund_total_return": fund_total_return}


def fit(series, *, trim=True, require_order=True):
    """Fit the existing trend and use sustained departures to set its edges."""
    if len(series) < 2 * DAYS or not series.index.is_unique or not series.index.is_monotonic_increasing:
        raise ValueError("duration channel requires ordered daily history")
    x = (series.index - series.index[0]).days.to_numpy() / 365.25
    y = np.log(series.to_numpy(dtype=float))
    if not np.isfinite(y).all():
        raise ValueError("duration channel levels must be positive and finite")
    slope, intercept = np.polyfit(x, y, 1)
    if trim:
        residual = y - (intercept + slope * x)
        keep = abs(residual) < 2 * residual.std()
        if keep.sum() < DAYS:
            raise ValueError("duration channel has too few observations after trimming")
        slope, intercept = np.polyfit(x[keep], y[keep], 1)
    trend = intercept + slope * x
    residual = pd.Series(y - trend)
    windows = residual.rolling(DAYS)
    # The least extreme day bounds the deviation sustained across each window.
    low = windows.max().quantile(.10)
    high = windows.min().quantile(.90)
    band = {key: float(np.exp(trend[-1] + move)) for key, move in zip("LMH", (low, 0, high))}
    ordered = 0 < band["L"] < band["M"] < band["H"]
    if require_order and not ordered:
        raise ValueError("duration channel does not bracket the trend")
    return {"anchors": band, "ordered": ordered, "slope": float(np.expm1(slope)),
            "days": DAYS, "observations": len(series), "start": series.index[0].date().isoformat(),
            "end": series.index[-1].date().isoformat()}


def dated_nav(snapshot, ticker, date):
    from lib.fund_history import normalize_fund_reference

    reference = snapshot["duration_reference"]
    flags = normalize_fund_reference(reference, ticker, date)
    if reference["kind"] != "fund_nav" or reference["date"] != date:
        raise ValueError("duration channel requires a same-day fund NAV")
    return reference, flags


def fund_channel(snapshot, ticker, instrument, expected_day):
    from lib.etf import SUBWINDOWS, slope_since
    from lib.value100_inputs import normalize_index_history

    data = normalize_index_history(snapshot, instrument)
    if min(data) > "2015-12-01" or max(data) != expected_day:
        raise ValueError("duration channel does not cover the declared index window")
    reference, flags = dated_nav(snapshot, ticker, expected_day)
    series = pd.Series(data, dtype=float)
    series.index = pd.to_datetime(series.index)
    result = fit(series)
    factor = reference["value"] / series.iloc[-1]
    result["anchors"] = {key: value * factor for key, value in result["anchors"].items()}
    result["subwindow_slopes"] = {start[:4]: slope_since(series, start) for start in SUBWINDOWS}
    result["index_level"] = float(series.iloc[-1])
    return result, series, float(factor), reference, flags


def fund_total_return(snapshot, ticker, first_day, expected_day):
    """Reinvest cash distributions from the dated NAV observations."""
    reference, _ = dated_nav(snapshot, ticker, expected_day)
    nav = pd.DataFrame.from_dict(snapshot["nav_history"], orient="index", dtype=float)
    nav.index = pd.to_datetime(nav.index, format="%Y-%m-%d")
    nav = nav.sort_index()
    if (not nav.index.is_unique or len(nav) < 500 or not np.isfinite(nav).all().all()
            or (nav.nav <= 0).any() or (nav.dividend < 0).any()
            or not np.allclose((nav.cumulative - nav.nav).diff().iloc[1:], nav.dividend.iloc[1:], atol=.00011)):
        raise ValueError("invalid NAV or cash-distribution history")
    nav = nav.loc[first_day:expected_day]
    if (nav.index[0].date().isoformat() != first_day or nav.index[-1].date().isoformat() != expected_day
            or nav.nav.iloc[-1] != reference["value"]):
        raise ValueError("fund total return does not match the dated NAV reference")
    total = ((nav.nav + nav.dividend) / nav.nav.shift()).fillna(1).cumprod()
    result = fit(total)
    result["anchors"] = {key: value * reference["value"] / total.iloc[-1]
                         for key, value in result["anchors"].items()}
    return result
