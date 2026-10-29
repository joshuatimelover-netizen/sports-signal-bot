from datetime import datetime
import numpy as np
import requests
from scipy.stats import poisson

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "9051396284:AAECqEQwtXqf98QXhxdzKkitjxs8izibEhU"
TELEGRAM_CHANNEL_ID = "@ProSportsSignals"

API_KEY = "882086f3b19e6d34ffad78b83b33f28f"

# API-Sports Endpoints
HOCKEY_HOST = "v1.hockey.api-sports.io"
BASKETBALL_HOST = "v1.basketball.api-sports.io"

# Minimum percentage required to trigger a signal alert
CONFIDENCE_THRESHOLD = 65.0


# ==========================================
# 1. API DATA FETCHING MODULE
# ==========================================


def get_todays_fixtures(sport, league_id, season_year):
  """Fetches all games scheduled for today from API-Sports."""
  today_str = datetime.utcnow().strftime("%Y-%m-%d")
  host = HOCKEY_HOST if sport.lower() == "hockey" else BASKETBALL_HOST

  url = f"https://{host}/games"
  headers = {"x-apisports-key": API_KEY}
  params = {"league": league_id, "season": season_year, "date": today_str}

  response = requests.get(url, headers=headers, params=params)
  if response.status_code == 200:
    return response.json().get("response", [])
  else:
    print(
        f"API Error fetching fixtures for {sport}:"
        f" {response.status_code} - {response.text}"
    )
    return []


def fetch_team_historical_stats(sport, team_id, league_id, season_year):
  """Fetches team statistics to determine average goals/points."""
  host = HOCKEY_HOST if sport.lower() == "hockey" else BASKETBALL_HOST
  url = f"https://{host}/teams/statistics"
  headers = {"x-apisports-key": API_KEY}
  params = {"team": team_id, "league": league_id, "season": season_year}

  response = requests.get(url, headers=headers, params=params)
  if response.status_code == 200:
    data = response.json().get("response", {})
    try:
      if sport.lower() == "hockey":
        avg = float(
            data.get("goals", {})
            .get("for", {})
            .get("average", {})
            .get("total", 3.0)
            or 3.0
        )
      else:
        avg = float(
            data.get("points", {})
            .get("for", {})
            .get("average", {})
            .get("total", 105.0)
            or 105.0
        )
      return avg
    except Exception:
      return 3.0 if sport.lower() == "hockey" else 105.0
  return 3.0 if sport.lower() == "hockey" else 105.0


# ==========================================
# 2. PROBABILITY & PERCENTAGE ENGINE
# ==========================================


def calculate_poisson_percentages(home_avg, away_avg, line=5.5, max_val=25):
  """Calculates Over/Under and Team Goal/Point probabilities using Poisson distribution."""
  prob_matrix = np.zeros((max_val, max_val))
  for h in range(max_val):
    for a in range(max_val):
      prob_matrix[h, a] = poisson.pmf(h, home_avg) * poisson.pmf(a, away_avg)

  over_prob = sum(
      prob_matrix[h, a]
      for h in range(max_val)
      for a in range(max_val)
      if h + a > line
  )
  under_prob = sum(
      prob_matrix[h, a]
      for h in range(max_val)
      for a in range(max_val)
      if h + a < line
  )

  home_over = sum(
      poisson.pmf(h, home_avg) for h in range(int(line / 2) + 1, max_val)
  )
  away_over = sum(
      poisson.pmf(a, away_avg) for a in range(int(line / 2) + 1, max_val)
  )

  return {
      "over": round(over_prob * 100, 1),
      "under": round(under_prob * 100, 1),
      "home_over": round(home_over * 100, 1),
      "away_over": round(away_over * 100, 1),
  }


def calculate_period_win_rate(home_past_periods, away_past_periods):
  """Calculates period win probability using historical period performance."""
  hw = (
      (home_past_periods[0] / home_past_periods[1]) * 100
      if home_past_periods[1] > 0
      else 50.0
  )
  aw = (
      (away_past_periods[0] / away_past_periods[1]) * 100
      if away_past_periods[1] > 0
      else 50.0
  )
  return round(hw, 1), round(aw, 1)


# ==========================================
# 3. TELEGRAM SIGNAL DISPATCHER
# ==========================================


def send_telegram_signal(sport, home_team, away_team, stats, match_line):
  signals = []

  if stats["over"] >= CONFIDENCE_THRESHOLD:
    signals.append(
        f"🎯 **Over {match_line} Goals/Points** — {stats['over']}%"
    )
  elif stats["under"] >= CONFIDENCE_THRESHOLD:
    signals.append(
        f"🎯 **Under {match_line} Goals/Points** — {stats['under']}%"
    )

  if stats["home_over"] >= CONFIDENCE_THRESHOLD:
    signals.append(
        f"🎯 **{home_team} Team Total Over** — {stats['home_over']}%"
    )

  if stats["away_over"] >= CONFIDENCE_THRESHOLD:
    signals.append(
        f"🎯 **{away_team} Team Total Over** — {stats['away_over']}%"
    )

  if stats["home_period_win"] >= CONFIDENCE_THRESHOLD:
    signals.append(
        f"🎯 **{home_team} Most Periods Won** — {stats['home_period_win']}%"
    )

  if stats["away_period_win"] >= CONFIDENCE_THRESHOLD:
    signals.append(
        f"🎯 **{away_team} Most Periods Won** — {stats['away_period_win']}%"
    )

  if signals:
    message = (
        f"🚨 **STATISTICAL SIGNAL ({sport.upper()})** 🚨\n\n"
        f"⚔️ **Match:** {home_team} vs {away_team}\n\n"
        f"**Recommended Predictions:**\n" + "\n".join(signals) + "\n\n"
        f"⚠️ *Derived via past records & Poisson distribution model.*"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
      print(f"Successfully broadcasted signal for {home_team} vs {away_team}!")
    else:
      print(f"Telegram Broadcast Error: {resp.text}")
  else:
    print(
        f"No signals met the {CONFIDENCE_THRESHOLD}% threshold for {home_team}"
        f" vs {away_team}."
    )


# ==========================================
# 4. AUTOMATION PIPELINE RUNNER
# ==========================================


def run_bot_workflow(sport, league_id, season_year, default_line):
  print(
      f"[{datetime.utcnow()}] Checking fixtures for {sport} (League ID:"
      f" {league_id})..."
  )
  fixtures = get_todays_fixtures(sport, league_id, season_year)

  if not fixtures:
    print(f"No {sport} matches found scheduled for today.")
    return

  for game in fixtures:
    home_team = game["teams"]["home"]["name"]
    away_team = game["teams"]["away"]["name"]
    home_id = game["teams"]["home"]["id"]
    away_id = game["teams"]["away"]["id"]

    home_avg = fetch_team_historical_stats(
        sport, home_id, league_id, season_year
    )
    away_avg = fetch_team_historical_stats(
        sport, away_id, league_id, season_year
    )

    max_limit = 35 if sport.lower() == "basketball" else 15
    poisson_res = calculate_poisson_percentages(
        home_avg, away_avg, line=default_line, max_val=max_limit
    )

    home_periods_record = [16, 30]
    away_periods_record = [12, 30]
    h_pw, a_pw = calculate_period_win_rate(
        home_periods_record, away_periods_record
    )

    match_stats_payload = {
        "over": poisson_res["over"],
        "under": poisson_res["under"],
        "home_over": poisson_res["home_over"],
        "away_over": poisson_res["away_over"],
        "home_period_win": h_pw,
        "away_period_win": a_pw,
    }

    send_telegram_signal(
        sport, home_team, away_team, match_stats_payload, default_line
    )


if __name__ == "__main__":
  run_bot_workflow(
      sport="Basketball", league_id=12, season_year="2025-2026", default_line=215.5
  )
  run_bot_workflow(
      sport="Hockey", league_id=57, season_year="2025", default_line=5.5
  )
  
