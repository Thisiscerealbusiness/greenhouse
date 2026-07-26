# Apple Tree Seasonal Watch

Automated Stockholm-temperature monitoring for a potted apple sapling,
implementing your Autumn/Winter/Spring trigger protocol and emailing
instructions at each confirmed transition. Runs on GitHub Actions, for free,
with no server or computer of yours needing to stay on.

## The three trigger points

| Point  | Value        | Direction | Why |
|--------|--------------|-----------|-----|
| Autumn | 10°C daily mean | at/below | Roughly where cooler nights + shortening days start pushing a deciduous tree toward leaf senescence. Used here as an early-warning signal to start tapering water/feed and get insulation materials ready — *not* to move the tree yet. |
| Winter | 2°C daily mean  | at/below | Deliberately set above 0°C. A small pot above ground has far less thermal mass than garden soil and freezes solid much faster than the air temperature would suggest, so the buffer exists to get the tree into the cellar *before* a hard frost reaches the root ball. |
| Spring | 5°C daily mean  | at/above | Apple chilling requirements (roughly 500–1000 hours below ~7°C) are comfortably met in Stockholm well before spring, so this threshold isn't about chilling — it's about avoiding moving the tree back into conditions that still swing below freezing at night. |

These are reasoned estimates, not lab-verified numbers for your specific
tree — edit the three constants at the top of `watch.py` if you want the
system more or less cautious.

## What the system does

Implements your state machine exactly:
- Default weekly temperature checks against whichever point is "live"
- Point reached → switch to daily checks
- 3 consecutive qualifying days → "trigger" → pause 1 week → re-check 3
  consecutive days → if repeated, "trigger confirmed"; if not, back to weekly
- Autumn trigger confirmed → email with dormancy-prep instructions (stays
  on balcony, tapering water/feed, get insulation ready)
- Winter trigger confirmed → email with cellar-move instructions, then
  switches to monthly checks (10th of each month) through March 10
- Monthly emails with visual-inspection tips while dormant
- Spring trigger confirmed → email with move-back-to-balcony instructions,
  then the whole cycle resets for next autumn

## Files

- `watch.py` — all the logic: SMHI fetch, state machine, email templates
- `state.json` — persisted state (created on first run, committed back by CI)
- `.github/workflows/watch.yml` — the daily scheduled job
