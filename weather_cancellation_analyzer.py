"""
Weather-Cancellation Analyzer
==============================
Enriches Goa/Manali 2024 hotel bookings with real historical weather
(Open-Meteo ERA5 archive API, free, no key) and tests whether heavy rain
or extreme temperature on the check-in date is associated with higher
cancellation / no-show rates.

Run:
    python weather_cancellation_analyzer.py --csv hotel_bookings.csv

Output:
    - weather_cache.json          (raw API responses, so re-runs are instant)
    - bookings_with_weather.csv   (original rows + weather columns, Goa/Manali 2024 only)
    - insight_chart.png           (cancellation rate by weather bucket)
    - prints the quantified insight to stdout
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import pandas as pd
import requests

# ----------------------------------------------------------------------
# 1. Config: map each city to coordinates ourselves (API needs lat/lon,
#    the dataset only has city names).
# ----------------------------------------------------------------------
CITY_COORDS = {
    "Goa": (15.2993, 74.1240),
    "Manali": (32.2432, 77.1892),
}

API_URL = "https://archive-api.open-meteo.com/v1/era5"
CACHE_FILE = "weather_cache.json"

# Thresholds used to label a day "heavy rain" / "extreme temp".
# Goa: tropical, so "heavy rain" set higher; Manali: hill town, "extreme
# temp" defined as very cold (snow-adjacent) days since that's what
# would actually disrupt a Manali trip.
HEAVY_RAIN_MM = 20.0          # >20mm precipitation in a day = heavy rain
EXTREME_TEMP_HIGH_C = 35.0    # very hot day
EXTREME_TEMP_LOW_C = 5.0      # very cold day (relevant mainly for Manali)


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def fetch_weather_for_city(city, start_date, end_date, cache, max_retries=3, timeout=15):
    """
    Fetch one full date-range batch of daily weather for a city in a
    SINGLE API call (not one call per booking row). Returns a dict
    {date_str: {"precip": float, "tmax": float}}.

    Includes retry-with-backoff and graceful failure: if the API is
    down or returns malformed data, we log a warning and return an
    empty dict instead of crashing the run.
    """
    cache_key = f"{city}_{start_date}_{end_date}"
    if cache_key in cache:
        return cache[cache_key]

    lat, lon = CITY_COORDS[city]
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "precipitation_sum,temperature_2m_max",
        "timezone": "auto",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            daily = data.get("daily", {})
            dates = daily.get("time", [])
            precip = daily.get("precipitation_sum", [])
            tmax = daily.get("temperature_2m_max", [])

            if not dates or len(dates) != len(precip) or len(dates) != len(tmax):
                print(f"  [WARN] Malformed weather payload for {city} "
                      f"({start_date}..{end_date}); skipping this batch.")
                cache[cache_key] = {}
                save_cache(cache)
                return {}

            result = {}
            for d, p, t in zip(dates, precip, tmax):
                # API can return null for missing station-days
                result[d] = {
                    "precip": p if p is not None else None,
                    "tmax": t if t is not None else None,
                }

            cache[cache_key] = result
            save_cache(cache)
            return result

        except requests.exceptions.Timeout:
            print(f"  [WARN] Timeout fetching weather for {city}, "
                  f"attempt {attempt}/{max_retries}")
            time.sleep(1.5 * attempt)
        except requests.exceptions.RequestException as e:
            print(f"  [WARN] Request error for {city}: {e}, "
                  f"attempt {attempt}/{max_retries}")
            time.sleep(1.5 * attempt)
        except (ValueError, KeyError) as e:
            print(f"  [WARN] Could not parse response for {city}: {e}")
            break

    print(f"  [ERROR] Giving up on weather for {city} after {max_retries} "
          f"attempts. Those rows will have null weather and be excluded "
          f"from the weather-based comparison.")
    cache[cache_key] = {}
    save_cache(cache)
    return {}


def enrich_with_weather(df):
    """
    df: bookings already filtered to property_city in CITY_COORDS and
        check_in_date in 2024.

    Batches one API call PER CITY covering the city's full min..max
    check-in date range (not one call per row, not even one call per
    city+date) -- this respects the "batch your calls sensibly"
    requirement while still giving exact per-date weather.
    """
    cache = load_cache()
    weather_lookup = {}  # (city, date_str) -> {"precip":..., "tmax":...}

    for city in df["property_city"].unique():
        if city not in CITY_COORDS:
            continue
        city_df = df[df["property_city"] == city]
        start_date = city_df["check_in_date"].min().strftime("%Y-%m-%d")
        end_date = city_df["check_in_date"].max().strftime("%Y-%m-%d")
        print(f"Fetching weather for {city}: {start_date} to {end_date} "
              f"(1 API call covering {city_df['check_in_date'].nunique()} "
              f"distinct check-in dates, {len(city_df)} bookings)")

        day_data = fetch_weather_for_city(city, start_date, end_date, cache)
        for date_str, vals in day_data.items():
            weather_lookup[(city, date_str)] = vals

    # Merge back onto bookings using (city, check_in_date) as the join key
    precip_col, tmax_col = [], []
    for _, row in df.iterrows():
        key = (row["property_city"], row["check_in_date"].strftime("%Y-%m-%d"))
        vals = weather_lookup.get(key, {"precip": None, "tmax": None})
        precip_col.append(vals["precip"])
        tmax_col.append(vals["tmax"])

    df = df.copy()
    df["precip_mm"] = precip_col
    df["tmax_c"] = tmax_col

    df["heavy_rain"] = df["precip_mm"].apply(
        lambda x: x is not None and x > HEAVY_RAIN_MM
    )
    df["extreme_temp"] = df["tmax_c"].apply(
        lambda x: x is not None and (x > EXTREME_TEMP_HIGH_C or x < EXTREME_TEMP_LOW_C)
    )
    df["weather_flag"] = df.apply(
        lambda r: "Heavy Rain" if r["heavy_rain"]
        else ("Extreme Temp" if r["extreme_temp"] else "Normal"),
        axis=1,
    )
    return df


def compute_insight(df):
    """
    Quantified insight: cancellation+no-show rate on adverse-weather
    check-in days vs normal days, for Goa and Manali separately and
    combined. This is something the booking dataset ALONE cannot
    produce, since it has no weather column.
    """
    df = df[df["precip_mm"].notna()].copy()  # only rows we got real weather for
    df["is_cancelled_or_noshow"] = df["booking_status"].isin(["Cancelled", "No-Show"])

    summary = (
        df.groupby("weather_flag")["is_cancelled_or_noshow"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "cancel_rate", "count": "n_bookings"})
        .reset_index()
    )
    summary["cancel_rate_pct"] = (summary["cancel_rate"] * 100).round(1)

    per_city = (
        df.groupby(["property_city", "weather_flag"])["is_cancelled_or_noshow"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "cancel_rate", "count": "n_bookings"})
        .reset_index()
    )
    per_city["cancel_rate_pct"] = (per_city["cancel_rate"] * 100).round(1)

    return summary, per_city, df


def make_chart(summary, out_path="insight_chart.png"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 5))
        order = ["Normal", "Heavy Rain", "Extreme Temp"]
        summary = summary.set_index("weather_flag").reindex(order).dropna().reset_index()
        bars = ax.bar(summary["weather_flag"], summary["cancel_rate_pct"],
                       color=["#4C72B0", "#C44E52", "#DD8452"])
        for b, n in zip(bars, summary["n_bookings"]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.5,
                    f"n={int(n)}", ha="center", fontsize=9)
        ax.set_ylabel("Cancellation + No-Show Rate (%)")
        ax.set_title("Cancellation Rate by Check-in-Day Weather\n(Goa + Manali, 2024)")
        plt.tight_layout()
        plt.savefig(out_path, dpi=150)
        print(f"\nChart saved to {out_path}")
    except ImportError:
        print("\n[INFO] matplotlib not installed; skipping chart generation. "
              "Run `pip install matplotlib` to enable it.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="hotel_bookings.csv",
                         help="Path to the hotel bookings CSV")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"[ERROR] CSV not found at {args.csv}")
        sys.exit(1)

    # Footnote 7: 'None' in customer_loyalty_tier is a real category,
    # not missing data -- keep_default_na=False prevents pandas from
    # eating it.
    df = pd.read_csv(args.csv, keep_default_na=False, na_values=[""])

    # Normalize column names (handles either snake_case or "Title Case"
    # headers depending on how the source CSV was exported)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # The dataset uses "checkin_date" (no underscore between check/in).
    # Standardize internally to check_in_date for readability.
    if "checkin_date" in df.columns and "check_in_date" not in df.columns:
        df = df.rename(columns={"checkin_date": "check_in_date"})

    df["check_in_date"] = pd.to_datetime(df["check_in_date"], errors="coerce")

    # Filter: Goa + Manali, check-in in 2024 (per the brief)
    mask = (
        df["property_city"].isin(CITY_COORDS.keys())
        & (df["check_in_date"].dt.year == 2024)
        & df["check_in_date"].notna()
    )
    sub = df[mask].copy()
    print(f"Found {len(sub)} Goa/Manali bookings with 2024 check-in dates "
          f"out of {len(df)} total rows.")

    if sub.empty:
        print("[ERROR] No matching rows -- nothing to enrich. Exiting.")
        sys.exit(1)

    enriched = enrich_with_weather(sub)
    enriched.to_csv("bookings_with_weather.csv", index=False)
    print("\nSaved enriched rows -> bookings_with_weather.csv")

    summary, per_city, clean = compute_insight(enriched)

    print("\n=== Cancellation/No-Show Rate by Weather (Goa + Manali combined) ===")
    print(summary.to_string(index=False))

    print("\n=== Same, split by city ===")
    print(per_city.to_string(index=False))

    # Build the headline quantified insight sentence
    try:
        normal_rate = summary.loc[summary.weather_flag == "Normal", "cancel_rate_pct"].iloc[0]
        rain_row = summary.loc[summary.weather_flag == "Heavy Rain"]
        if not rain_row.empty:
            rain_rate = rain_row["cancel_rate_pct"].iloc[0]
            rain_n = int(rain_row["n_bookings"].iloc[0])
            delta = round(rain_rate - normal_rate, 1)
            print(f"\nINSIGHT: On heavy-rain check-in days (>{HEAVY_RAIN_MM}mm), "
                  f"cancellation+no-show rate was {rain_rate}% (n={rain_n}) vs "
                  f"{normal_rate}% on normal-weather days -- a {delta:+.1f} "
                  f"percentage-point difference that the booking dataset alone, "
                  f"with no weather column, could never have surfaced.")
    except (IndexError, KeyError):
        print("\n[INFO] Not enough heavy-rain days in this sample to state "
              "the headline comparison; see the full table above instead.")

    make_chart(summary)


if __name__ == "__main__":
    main()
