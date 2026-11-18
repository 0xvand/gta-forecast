[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/0xvand/gta-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/0xvand/gta-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU forecast — make.fun entry

Entry for **gta6-twitch-ccu-forecast-01** ("Forecast GTA VI's launch-day Twitch viewers
hour by hour"). `main.py` reads each case in the input directory and writes, for hours
2–24 of the release day, five quantiles of the Twitch category's concurrent viewers,
anchored on hour 1's print and shaped by the release-day curves of the comparable
launches inside the case file.

- `METHOD.md` — the model, the evidence behind it, backtest results, and assumptions.
- `tools/backtest.py` — leave-one-out validation over a case file's comparables:
  `python3 tools/backtest.py <case.in>` (add `--grid` for the calibration grid).
  - Run locally: `MAKEFUN_INPUT_DIR=<dir with .in files> MAKEFUN_OUTPUT_DIR=<out> python3 main.py`

  MIT licensed (see `LICENSE`).
  
