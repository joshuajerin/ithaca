from __future__ import annotations


def make_fetch(series_by_symbol: dict[str, list[float]], dates: list[str]):
    def _fetch(symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
        su = symbol.upper()
        if su not in series_by_symbol:
            raise ValueError(f"no data for {su}")
        closes = series_by_symbol[su]
        points = [
            {
                "d": dates[i],
                "o": closes[i],
                "h": closes[i],
                "l": closes[i],
                "c": closes[i],
                "v": 1_000_000.0,
            }
            for i in range(len(dates))
        ]
        return {
            "points": points,
            "quote": {"symbol": su, "price": closes[-1], "asOf": dates[-1] + "T20:00:00Z"},
        }

    return _fetch
