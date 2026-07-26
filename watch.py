#!/usr/bin/env python3
"""
Apple Tree Seasonal Watch
--------------------------
Tracks Stockholm temperature via SMHI's open data API and drives a
three-season state machine (Autumn / Winter / Spring) for a potted apple
sapling, emailing instructions at each confirmed transition.

Designed to be run ONCE PER DAY by a scheduler (GitHub Actions cron).
State persists in state.json, which the workflow commits back to the repo
after every run, so the script is stateless between invocations.

--------------------------------------------------------------------------
THE THREE TRIGGER POINTS (see README.md for the reasoning behind each)
--------------------------------------------------------------------------
AUTUMN_POINT = 10.0  (°C, daily mean)  -> start prepping for dormancy
WINTER_POINT = 2.0   (°C, daily mean)  -> move pot into the cellar
SPRING_POINT = 5.0   (°C, daily mean)  -> move pot back to the balcony

Adjust these three constants if you want the system more/less cautious.
--------------------------------------------------------------------------
"""

import json
import os
import smtplib
import ssl
import sys
import urllib.request
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

AUTUMN_POINT = 10.0
WINTER_POINT = 2.0
SPRING_POINT = 5.0

# SMHI station: Stockholm-Observatoriekullen A (central Stockholm, parameter 2
# = "Dygnsmedelvärde" / daily mean temperature). Change if you want a station
# closer to Kista specifically (e.g. Bromma, id 97390).
SMHI_STATION_ID = "98230"
SMHI_PARAMETER = "2"  # daily mean temperature
SMHI_URL = (
    f"https://opendata-download-metobs.smhi.se/api/version/1.0/"
    f"parameter/{SMHI_PARAMETER}/station/{SMHI_STATION_ID}/period/latest-months/data.json"
)

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")

EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_TO = os.environ.get("EMAIL_TO")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------
# phase:            "pre_autumn" | "post_autumn" | "post_winter" | "post_spring"
# mode:              "weekly" | "daily" | "await_confirm" | "monthly"
# point_name:         which point we're currently watching for
# streak:            list of recent qualifying daily temps (for 3-in-a-row check)
# last_check_date:   ISO date string of the last time we actually queried SMHI
# awaiting_confirm_since: ISO date string - when we start the 1-week wait
# monthly_next_date: for the Nov-Mar monthly cadence (10th of month)

DEFAULT_STATE = {
    "phase": "pre_autumn",
    "mode": "weekly",
    "point_name": "autumn",
    "streak": [],
    "last_check_date": None,
    "awaiting_confirm_since": None,
    "monthly_next_date": None,
    "log": [],
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return dict(DEFAULT_STATE)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log(state, msg):
    stamp = datetime.utcnow().isoformat(timespec="seconds")
    print(f"[{stamp}] {msg}")
    state["log"] = (state.get("log") or [])[-50:] + [f"{stamp} {msg}"]


# ---------------------------------------------------------------------------
# SMHI
# ---------------------------------------------------------------------------

def fetch_latest_daily_mean():
    """Return (date, temp_c) for the most recent completed day available."""
    with urllib.request.urlopen(SMHI_URL, timeout=30) as resp:
        data = json.load(resp)
    values = data.get("value", [])
    if not values:
        raise RuntimeError("SMHI returned no values")
    latest = values[-1]
    dt = datetime.utcfromtimestamp(latest["date"] / 1000).date()
    temp = float(latest["value"])
    return dt, temp


# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------

def send_email(subject, body):
    if not (EMAIL_FROM and EMAIL_TO and EMAIL_APP_PASSWORD):
        print("Email not configured (EMAIL_FROM/EMAIL_TO/EMAIL_APP_PASSWORD missing) "
              "-- printing instead of sending:\n")
        print(f"SUBJECT: {subject}\n\n{body}")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
    print(f"Email sent: {subject}")


# ---------------------------------------------------------------------------
# MESSAGE TEMPLATES
# ---------------------------------------------------------------------------

AUTUMN_MSG = """AUTUMN TRIGGER CONFIRMED

Stockholm's daily mean temperature has stayed at or below {point}C for
three consecutive days, twice a week apart. Your apple sapling's dormancy
process is starting.

Keep it on the balcony for now -- do NOT move it yet. Do this instead:

1. Stop fertilizing completely (feeding now works against dormancy).
2. Taper watering -- water only when the top 2-3cm of soil is dry.
3. Let it drop its leaves naturally. Do not pull leaves off by hand.
4. Get winter gear ready this week so you're not scrambling later:
   - Fiberduk (garden fleece) or juteväv, to wrap the crown if an early
     hard frost hits before you've moved it to the cellar
   - Bubbelplast (bubble wrap) or a kokosmatta, to insulate the pot itself
   - A sheet of frigolit (styrofoam board) to stand the pot on -- cold
     travels up through a balcony floor fast
   - (Optional) an insulated "krukskydd" pot cosy if you'd rather buy one
     ready-made -- Plantagen, Wexthuset, and Granngården all stock these

You'll get another email with move-to-cellar instructions once the
Winter trigger is confirmed.
"""

WINTER_MSG = """WINTER TRIGGER CONFIRMED -- MOVE TO THE CELLAR NOW

Stockholm's daily mean temperature has stayed at or below {point}C for
three consecutive days, twice a week apart. It's time to move the tree
into cellar storage before a hard frost catches the root ball.

How to move it:
1. Water it well the day before the move -- moist (not soggy) soil
   insulates roots better than dry soil.
2. Check that the leaves have mostly dropped. If a few stubborn leaves
   remain, that's fine -- leave them, don't pull them.
3. Carry the pot down as-is; no need to wrap it just to move it.
4. In the cellar: place it away from any heat source (boiler, heated
   wall, pipes). Ideal spot is a consistently cool 0-5C.
5. Stand the pot on a piece of frigolit or wood, not directly on cold
   concrete.
6. No light needed -- it's dormant and not photosynthesizing.
7. Water sparingly from now on: just enough that the soil never goes
   bone dry. Roughly once a month is typical, more if the cellar is dry.

You'll get a monthly check-in email with inspection tips until the
Spring trigger is confirmed. Mark the pot now if you have other plants
stored nearby -- a leafless sapling in January is hard to identify later.
"""

MONTHLY_MSG = """MONTHLY DORMANCY CHECK-IN

Just a reminder to give the apple sapling a quick look this week while
it's in cellar storage.

Check for:
- Soil moisture: push a finger 2-3cm in. If bone dry, water lightly.
  If wet/soggy, hold off -- overwatering in dormancy risks root rot.
- Stem firmness: gently flex a small branch. It should be flexible and
  green/tan under the bark if you nick it lightly with a nail. Black,
  brittle, or hollow-feeling wood is a bad sign.
- Mold or mildew on the soil surface or stem -- wipe away, improve
  airflow around the pot if you see this.
- Pests: check for anything unusual, though this is rare in cold
  dormant storage.
- General shrivel: the stem itself should not look shriveled or
  wrinkled -- that indicates the roots have dried out too much.

No action needed if everything looks normal -- just keep waiting for
spring. Next check-in is next month (or when the Spring trigger fires,
whichever comes first).
"""

SPRING_MSG = """SPRING TRIGGER CONFIRMED -- MOVE BACK TO THE BALCONY

Stockholm's daily mean temperature has stayed at or above {point}C for
three consecutive days, twice a week apart. Winter chilling is long
since satisfied (apple trees typically need this by January), so it's
safe to bring the tree back into active growing conditions.

How to move it:
1. Don't rush straight to a full sunny balcony spot from day one. Move
   it out and give it a few hours a day in indirect light for the first
   week (a shaded balcony corner is fine), then increase exposure.
2. Resume normal watering: water when the top few cm of soil are dry,
   same as any actively growing potted plant.
3. Wait for visible bud swell before treating it as "fully awake" --
   don't fertilize until you see new green growth.
4. Once new growth appears, consider repotting one size up if roots are
   visibly circling the drainage holes or poking out the bottom --
   spring, right as growth resumes, is the best time to do this.
5. Watch the forecast for the next couple of weeks -- a late-spring
   frost can still occur in Stockholm even after this trigger; if a
   hard frost (below -2C) is forecast, bring it in for that night or
   cover it with fiberduk.

That's the full cycle. The system now resets and will watch for next
autumn's trigger starting this coming season.
"""


# ---------------------------------------------------------------------------
# STATE MACHINE HELPERS
# ---------------------------------------------------------------------------

def point_for(name):
    return {"autumn": AUTUMN_POINT, "winter": WINTER_POINT, "spring": SPRING_POINT}[name]


def qualifies(name, temp):
    """Does this single day's temperature qualify toward a streak for `name`?"""
    p = point_for(name)
    if name == "spring":
        return temp >= p
    return temp <= p


def next_point_after(name):
    return {"autumn": "winter", "winter": "spring", "spring": "autumn"}[name]


def should_check_today(state, today):
    mode = state["mode"]
    last = state["last_check_date"]
    if mode == "daily":
        return last != str(today)
    if mode == "weekly":
        if last is None:
            return True
        return (today - date.fromisoformat(last)).days >= 7
    if mode == "await_confirm":
        since = state["awaiting_confirm_since"]
        # Wait exactly one week from when the first trigger fired, then
        # resume DAILY checks for the confirmation streak.
        if since is None:
            return True
        return today >= (date.fromisoformat(since) + timedelta(days=7))
    if mode == "monthly":
        nxt = state.get("monthly_next_date")
        if nxt is None:
            return True
        return today >= date.fromisoformat(nxt)
    return True


def advance_monthly_date(today):
    """Next occurrence of the 10th of a month, after `today`."""
    year, month = today.year, today.month
    month += 1
    if month > 12:
        month = 1
        year += 1
    return date(year, month, 10)


def run():
    state = load_state()
    today = date.today()

    if not should_check_today(state, today):
        log(state, f"Nothing scheduled for today ({today}); phase={state['phase']} mode={state['mode']}")
        save_state(state)
        return

    obs_date, temp = fetch_latest_daily_mean()
    log(state, f"SMHI daily mean for {obs_date}: {temp}C "
               f"(watching '{state['point_name']}', mode={state['mode']})")
    state["last_check_date"] = str(today)

    name = state["point_name"]
    point = point_for(name)
    q = qualifies(name, temp)

    if state["mode"] == "weekly":
        if q:
            log(state, f"{name.capitalize()} point ({point}C) reached on weekly check -> switching to daily watch")
            state["mode"] = "daily"
            state["streak"] = [temp]
        else:
            state["streak"] = []

    elif state["mode"] in ("daily", "await_confirm"):
        state["streak"].append(temp) if q else state.__setitem__("streak", [])
        if len(state["streak"]) >= 3:
            if state["mode"] == "daily":
                log(state, f"{name.capitalize()} TRIGGER (3-in-a-row at/past {point}C). "
                           f"Pausing for 1 week, then re-checking.")
                state["mode"] = "await_confirm"
                state["awaiting_confirm_since"] = str(today)
                state["streak"] = []
            else:
                # This is the confirmation run, one week later
                log(state, f"{name.capitalize()} TRIGGER CONFIRMED.")
                fire_confirmation(state, name, point)
                state["streak"] = []
        elif state["mode"] == "await_confirm" and state["streak"] == []:
            # confirmation attempt failed -- did not repeat -> back to weekly
            log(state, f"{name.capitalize()} trigger did not repeat -> reverting to weekly monitoring")
            state["mode"] = "weekly"
            state["awaiting_confirm_since"] = None

    elif state["mode"] == "monthly":
        # Monthly cadence only applies during winter dormancy per spec.
        send_email("Apple tree: monthly dormancy check-in", MONTHLY_MSG)
        log(state, "Sent monthly dormancy check-in email")
        if today >= date(today.year if today.month >= 3 else today.year, 3, 10) and today.month == 3:
            log(state, "March 10 monthly check done -> reverting to weekly monitoring for Spring point")
            state["mode"] = "weekly"
            state["monthly_next_date"] = None
        else:
            state["monthly_next_date"] = str(advance_monthly_date(today))
        # Still check whether spring point already qualifies, without breaking cadence
        if qualifies("spring", temp):
            log(state, "(Note: spring point already met during monthly check, "
                       "but per protocol spring-point monitoring only formally begins in March.)")

    save_state(state)


def fire_confirmation(state, name, point):
    if name == "autumn":
        send_email("Apple tree: Autumn trigger confirmed - prep started", AUTUMN_MSG.format(point=point))
        state["phase"] = "post_autumn"
        state["point_name"] = "winter"
        state["mode"] = "weekly"
        state["awaiting_confirm_since"] = None

    elif name == "winter":
        send_email("Apple tree: Winter trigger confirmed - move to cellar", WINTER_MSG.format(point=point))
        state["phase"] = "post_winter"
        state["point_name"] = "spring"
        state["awaiting_confirm_since"] = None
        # Enter the Nov-Mar monthly cadence, checked on the 10th of each month
        today = date.today()
        state["monthly_next_date"] = str(advance_monthly_date(today))
        state["mode"] = "monthly"
        # Send the first monthly check-in right away too
        send_email("Apple tree: monthly dormancy check-in", MONTHLY_MSG)

    elif name == "spring":
        send_email("Apple tree: Spring trigger confirmed - move to balcony", SPRING_MSG.format(point=point))
        # Reset for next cycle
        state["phase"] = "pre_autumn"
        state["point_name"] = "autumn"
        state["mode"] = "weekly"
        state["awaiting_confirm_since"] = None
        state["monthly_next_date"] = None


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
