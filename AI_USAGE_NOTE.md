## AI Usage Note

- Used Claude to draft the first version of `fetch_weather_for_city`. Initial draft had no retry logic and would crash the whole run with an unhandled `requests.exceptions.Timeout` on a single bad call — I added the retry-with-backoff loop and made failures degrade to an empty dict (so affected rows get null weather instead of killing the script).
- First draft batched per (city, date) — i.e. one API call per distinct check-in date — which would have meant ~400+ calls. I changed it to one call per city covering the full min→max date range, since Open-Meteo returns a whole date range's daily series in a single response.
- Caught and fixed a join bug: AI's first merge used `pd.merge` on a raw `date` column where bookings had `datetime64` but the API dates were strings — silently produced all-null weather columns. Rewrote as an explicit `.strftime("%Y-%m-%d")` dict-lookup join so the key types always match.
- I added the `keep_default_na=False` read (Footnote 7) and the column-name normalization myself; AI's draft assumed clean lowercase snake_case headers, which wasn't a safe assumption for this CSV.
