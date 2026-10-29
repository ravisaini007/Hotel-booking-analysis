# Hotel Booking Cancellation Analysis

**Tools:** Python (Pandas, Matplotlib, Seaborn, SciPy) · SQL (MySQL) · Business Analysis

An end-to-end analysis of 12,000 hotel bookings from an online booking platform. The goal: find where cancellations are concentrated, diagnose the cause with hypothesis tests, and recommend one targeted, quantified intervention.

---

## Business Problem

The platform's cancellation rate is **19.18%** against an industry benchmark of **12%**, a gap of **7.18 percentage points (pp)**. The board wants it cut by 5 pp (to about 14%) within two quarters. The Operations head asked for numbers and counterfactuals, not generic policy advice.

## Dataset

| Item | Detail |
|---|---|
| File | `hotel_bookings.csv` |
| Size | 12,000 bookings × 28 columns (one row per booking) |
| Period | Check-in dates from 1 Jan 2024 to 31 Dec 2024 |
| Status mix | 9,333 Completed · 2,302 Cancelled · 365 No-Show |
| Content | Customer, property, dates, room, channel, pricing, payment, status, review |

### Data quality issues handled

| Issue | Treatment |
|---|---|
| Invalid stays (checkout on or before check-in) | **120 rows** identified and excluded from revenue |
| Booking date earlier than customer signup date | Flagged and excluded from realized revenue |
| `num_rooms = 0` rows (amount = 0) | Treated as errors and excluded |
| Property names repeat across cities | Always grouped on `property_id`, never on name |
| Reviews on Cancelled bookings | Flagged as impossible |
| Review scale: 1–5 (Individual, Group) vs 1–10 (Corporate) | Normalised to a 5-point scale before comparing segments |
| Loyalty tier `'None'` read as missing by Pandas | Loaded with `keep_default_na=False` |
| Cancelled and No-Show rows still carry an amount | Realized revenue counts **Completed** bookings only |

**Data quality results**

- Invalid stays: **120**
- Normalised mean review rating: Individual **3.77**, Group **3.77**, Corporate **3.62**. Corporate guests are slightly less satisfied.
- Realized revenue, Luxury properties (after footnotes 1, 2, 3, 8): **₹89,009,636.79**

---

## Key Findings

### 1. Where is the problem concentrated?

Cancellation rate by booking channel (platform-wide):

| Channel | Bookings | Cancelled | Rate |
|---|---:|---:|---:|
| OTA | 4,245 | 937 | 22.07% |
| Corporate Portal | 3,213 | 650 | 20.23% |
| Travel Agent | 2,414 | 399 | 16.53% |
| Direct Website | 2,128 | 316 | 14.85% |

Channel explains only a **7.2 pp** spread, customer segment **0.8 pp**, and loyalty tier **7.5 pp**. **Property city × calendar month** shows a spread of **52.6 pp**, so cancellations are concentrated in specific places and times, not spread evenly.

<!-- Add your charts after exporting them from the notebook:
![Cancellation rate by channel and lead time](images/chart1_channel_leadtime.png)
![Cancellation rate by city and month](images/chart2_city_month_heatmap.png)
-->

### 2. Rate vs. volume

The worst-rate slices are not the biggest-volume slices. Goa and Kochi in the summer months top the rate ranking, while the largest cancellation counts come from big, ordinary city-months (for example Pune in November, Chennai in March). A small slice with a very high rate barely moves the platform-wide number, which matters for a 5 pp target.

### 3. Root cause: Goa in June (57 bookings, 30 cancelled, 52.63%)

Three explanations were tested side by side:

| Hypothesis | Evidence | Verdict |
|---|---|---|
| **Lead-time effect** | Mean lead time 38.2 vs 32.5 days, medians equal (15 days). Welch's t-test p = 0.6875 | Rejected |
| **Channel-mix effect** | Goa-June's channel mix predicts only **17.74%** cancellations, but the actual rate is **52.63%** | Rejected |
| **City + season effect** | Goa in other months: 24.46%. Other cities in June: 19.52%. Chi-square p < 0.0001 | **Supported** |

**Conclusion:** the hotspot is a genuine Goa × June interaction, not a booking-behaviour or channel-mix artefact.

<!-- ![Goa June diagnosis](images/chart3_goa_june_diagnosis.png) -->

---

## Recommendation

**Introduce a 20% non-refundable deposit for Goa bookings with June stays, across all channels.**

- **Who:** Goa, June stays, all channels
- **What:** 20% non-refundable deposit at booking. Customers can still cancel, but forfeit the deposit.
- **Expected impact:** assuming the deposit cuts cancellations in this slice by 20–40%:
  - Prevented cancellations = 30 × (20% to 40%) = **6 to 12 bookings**
  - Platform effect = (6 to 12) ÷ 12,000 = **0.05 to 0.10 pp**
- **Risk:** price-sensitive travellers may move to competitors that offer free cancellation, reducing bookings in the segment.

**Honest read of the numbers:** this is a precise, low-risk pilot, but it is **far too small to deliver the board's 5 pp target on its own**. The 20–40% effect is an assumption, not something measured in this dataset.

### Next step worth testing (back-of-envelope, not part of the original submission)

Channels are a bigger lever by volume. If OTA and Corporate Portal cancellation rates fell to the Direct Website level (14.85%), cancellations would drop by roughly (4,245 × 7.22%) + (3,213 × 5.38%) ≈ 479, or about **4.0 pp** platform-wide. This is an upper bound and should be validated with an A/B test.

---

## SQL Work

A normalised schema (`customers`, `properties`, `bookings`) with primary and foreign keys, `NOT NULL`, and constraints tied to the data quirks:

- `CHECK (checkout_date > checkin_date)` for invalid stays
- `UNIQUE (property_name, property_city)` for repeated property names
- `CHECK` constraints on segment, loyalty tier, and booking status

Queries (window functions):

- **Top property per city by realized revenue**, using `RANK() OVER (PARTITION BY property_city ORDER BY revenue DESC)`. Examples: Goa → Sapphire Retreat (₹19.6M), Chennai → Saffron Heights (₹14.4M), Udaipur → Hilltop Inn (₹15.7M).
- **Customers with an average gap under 30 days** between Completed bookings, using `LAG()`. Result: **0 customers**.

---

## Repository Contents

```
├── README.md
├── Answers.pdf          # Full write-up: data quality, case study, SQL
├── hotel_bookings.csv   # Source data (12,000 rows)
└── SET-_A.pdf           # Original assessment brief
```

<!-- Add your notebook/SQL files here if you upload them, for example:
├── code/analysis.ipynb
├── code/schema_and_queries.sql
└── images/
-->

## How to Reproduce

```python
import pandas as pd

df = pd.read_csv("hotel_bookings.csv", keep_default_na=False, na_values=[""])
for c in ["booking_date", "checkin_date", "checkout_date"]:
    df[c] = pd.to_datetime(df[c], dayfirst=True)

df["cancelled"] = df["booking_status"].eq("Cancelled")
print(f"Platform cancellation rate: {df['cancelled'].mean():.2%}")   # 19.18%
```

Use `keep_default_na=False` so the loyalty tier `'None'` is not read as missing.

## Limitations

- Goa-June rests on **57 bookings**, a small sample. The result is statistically significant, but the exact rate could move with more data.
- One year of data cannot separate a recurring June pattern from a one-off event.
- The root cause is established statistically (*where* and *when*), not *why*. Weather, local events, or price changes are untested here.
- The deposit impact range is an assumption, not an estimate from experiment.

## Author

**Your Name** · [LinkedIn](https://www.linkedin.com/in/your-handle) · [GitHub](https://github.com/your-handle)
