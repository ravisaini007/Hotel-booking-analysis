## Weather-Cancellation Analyzer

**What it does:** Pulls real historical daily weather (rain + max temp) for every Goa/Manali check-in date in 2024 from Open-Meteo, joins it onto the bookings, and quantifies whether heavy-rain or extreme-temperature check-in days have a higher cancellation+no-show rate than normal-weather days.

**How to run:** `pip install pandas requests matplotlib` then `python weather_cancellation_analyzer.py --csv hotel_bookings.csv` (run from a machine with internet access — outputs `bookings_with_weather.csv`, `insight_chart.png`, and prints the headline insight to stdout).

**Design decision:** Weather is fetched with exactly ONE API call per city (covering that city's full min→max check-in date range, ~2 calls total) instead of one call per booking or per date, then joined back in-memory on `(city, date)` — this keeps the tool well under any reasonable rate limit even on the full 12,000-row dataset.

**Limitation:** Open-Meteo's ERA5 archive reports weather at a single lat/lon per city, so it can't capture intra-city variation (e.g. a property on a Goa hillside vs. one on the beach); it's a city-level weather proxy, not a property-level one.



