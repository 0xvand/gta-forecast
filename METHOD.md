# Method — GTA VI launch-day Twitch CCU forecast

## The task

For the release day of Grand Theft Auto VI (Thursday **2026-11-19**, UTC), forecast the
Twitch "Grand Theft Auto VI" category's concurrent viewers in each of hours 2–24, as five
quantiles (5/25/50/75/95%), given everything recorded up to the end of hour 1 — including
hour 1's own count. Scoring is mean pinball loss on the log scale, so the forecast must be
right in *ratio* terms and honestly spread. The entry is `main.py` (Python 3.13, standard
library only, deterministic, ~0.1 s per case against an 8 s cap).

## Evidence base

- **Launch**: 2026-11-19 on PS5 and Xbox Series X|S only (no PC at launch), single-player,
  unlocking at **midnight local time rolling around the world** — New Zealand first
  (2026-11-18T11:00Z), central Europe 23:00Z, UK 00:00Z, US East 05:00Z, US West 08:00Z.
  Preload opened 2026-11-10; Take-Two says pre-orders are "tracking far in excess" of
  expectations (~15.9M digital pre-orders by 2026-11-17, Sensor Tower estimate).
- **Demand records**: Trailer 1 drew 93M YouTube views in 24 h (a non-music debut record);
  Trailer 2 drew ~475M cross-platform views in 24 h, called the biggest video launch of
  all time. GTA V has shipped ~215–235M copies; this is the first sequel in 13 years.
- **The category itself**: at the 2026-08-27 "Extended Look" premiere, the GTA VI Twitch
  category averaged **1,418,094 viewers in its peak hour** (SullyGnome hourly data, inside
  every case file as a comparable) — for a video premiere, with no game playable. Its
  ordinary pre-launch level is ~1,400–2,600 viewers.
- **Launch-day Twitch records to beat**: Hogwarts Legacy peaked at ~1.28M concurrent
  viewers (single-player record, Feb 2023), Cyberpunk 2077 at ~1.14M (Dec 2020), Elden
  Ring at ~875k in its biggest hour. A GTA VI launch-day peak above all of these is the
  central expectation, not the tail.

## The model

The program never guesses a level: hour 1's print `p` sets the level, and the model
forecasts the day's *shape* as ratios to hour 1, learned from the case's own library of
38–42 comparable launches (SullyGnome hourly category averages, 14 days before to 3 days
after each launch).

1. **Curves.** Each usable comparable (hour 1 present and positive, ≥20 of the day's 24
   hours sampled) contributes log ratios `log(viewers_h / viewers_1)` for h = 1..24;
   missing hours are log-interpolated. The pre-release GTA VI category "comparable" has
   no release day and drops out by this rule.
2. **Weights.** A comparable counts more the more its launch resembles the target:
   - *Unlock pattern* (parsed from the kit's research notes): rolling midnight-local
     ×1.6; a single fixed-hour global unlock ×0.45; unrecorded ×0.8.
   - *Early access*: a paid early-access window before the "release" day ×0.55 (its day
     shape is contaminated — the real first day was earlier).
   - *Platforms*: no PC in the list ×1.3 (the target is console-only).
   - *Genre*: multiplayer / live-service / free-to-play launches ×0.7 (the target is
     single-player).
   - *Regime*: the comparable's viewer ramp over the 12 hours before its hour 1 (log
     space, relative to its hour 1) is compared with the case's own ramp from
     `history_hourly`; weight × `exp(-distance / 1.4)`. This separates launches already
     hot at hour 1 (unlocked region by region beforehand — GTA VI's situation) from
     launches that unlocked hours into the UTC day and ramped from near zero.
   - *Scale*: weight × `exp(-|log v1 − log p| / 1.0)` — the biggest launches saturate
     early and decay; small ones are still building at midnight.
3. **Median.** For hour h, `q50 = p · exp(weighted median of the log ratios at h)`.
4. **Spread.** The weighted standard deviation of the log ratios at h around the centre,
   × 0.8, floored at 0.12 log units; quantiles are `q50 · exp(z_τ · s_h)` with the
   normal's z at the five levels. Constants (0.8, 1.0, 1.4, the shape weights) were
   calibrated on the backtest below, choosing the middle of a broad plateau rather
   than the arg-min, to avoid overfitting 37 folds.

## Validation

There is no local grade (the server grades), so the model is validated by
**leave-one-out backtest** (`tools/backtest.py`): every comparable in a practice case
takes a turn as the target — the model sees only its hour-1 viewers and the other
comparables — and is scored with the contest's exact pinball loss against its real day.

- All 37 folds: **model 0.461 vs house persistence baseline 0.930**.
- The 11 rolling-midnight folds (the regime GTA VI and all four practice launches are
  in): **model 0.239 vs baseline 0.357**. For reference, the baseline scores 0.387 on
  the real practice set; the model must also beat the house *model* forecast on the
  final to take a prize, which is why the spread is calibrated, not just the median.
- Outputs verified: exact format (23 rows, hours 2–24, five non-decreasing finite
  quantiles in (0, 1e9], ≤ 65,536 bytes), byte-identical across two runs, ~0.09 s per
  case run the way the grader runs it (one case per sandbox).

## Headline scenario (what the model says about GTA VI itself)

The final case's hour-1 print does not exist until 2026-11-19T01:00Z, so the forecast is
a curve of ratios. Anchored at an assumed hour-1 print of **700,000** (reasoned from
Elden Ring's 875k hour 1 under the same rolling unlock, tempered by GTA VI's hour 1
falling at 00:00–01:00Z before the US unlocks), the model's median path is:

- **Peak ≈ 876,000 concurrent viewers at hour 19 (18:00–19:00Z)**, with the 90% band at
  that hour running to ~1.71M — the band, not the median, is where a premiere-scale
  1.4M+ hour would land. Peak ratio ≈ 1.25× hour 1; the day's second wind (US afternoon
  into European prime) beats the launch-morning level.
- **Shape**: high at hours 1–2 (UK/EU unlock, APAC already in), a sag through hours
  8–11 (07:00–11:00Z), the US East (05:00Z) and West (08:00Z) unlock bumps absorbed in
  hours 5–8, then a long build from hour 14 to the 17–21 peak block, still ~672k
  median at hour 24 as US prime time begins.
- **Total ≈ 14.3M viewer-hours** across the 24 hours on the median path (8.5M at a
  400k hour-1 anchor; 18.4M at a 1.0M anchor).

## Assumptions and limits

- Hour 1's print is taken as given; all level risk sits in it. If Twitch's directory
  count is distorted in hour 1 (e.g. a front-page feature inflating it), ratios inherit
  the distortion proportionally.
- Comparables are SullyGnome *hourly averages*; the final's prints are means of minute
  reads. The measures are close but not identical — one reason the spread is kept
  honest rather than tuned to the floor.
- GTA VI is bigger than every comparable. Ratios are scale-free, but a launch this
  large may saturate (or break) shapes no comparable shows; the scale weighting leans
  on the largest launches for exactly this reason.
- The model uses no information outside the case file at run time: the web research
  above informed the design and this document, never the numbers, which must come from
  the sealed data so the practice and the final are forecast by the same rule.
