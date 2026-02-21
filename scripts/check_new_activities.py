#!/usr/bin/env python3
"""
New activity checker for GitHub Actions.

Polls Strava for new running activities since the last known activity ID.
When a new activity is found, analyzes it and sends a Discord notification.

The last seen activity ID is stored in .last_activity_id in the repo root
and updated via git commit by the workflow after each new notification.

Usage (via GitHub Actions):
    uv run python scripts/check_new_activities.py

Output (stdout, parsed by workflow):
    NEW_ACTIVITY_ID=<id>   (printed if a new activity was found)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.analyzer import analyze
from src.advisor import generate_single_activity_advice
from src.models import TrainingZones
from src.notifier import send_new_activity_notification
from src.race_manager import load_races
from src.strava_client import StravaClient

STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".last_activity_id"
)


def read_last_id() -> int:
    try:
        with open(STATE_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_last_id(activity_id: int) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(str(activity_id) + "\n")


def main() -> None:
    last_id = read_last_id()
    aet_hr = int(os.getenv("ATHLETE_AET_HR", "150"))
    ant_hr = int(os.getenv("ATHLETE_ANT_HR", "170"))

    print(f"前回の最終アクティビティID: {last_id}")

    client = StravaClient()

    # Fetch most recent 5 running activities (fast check)
    try:
        recent = client.fetch_activities(weeks=1)
    except Exception as e:
        print(f"ERROR: Strava APIからのデータ取得に失敗: {e}", file=sys.stderr)
        sys.exit(1)

    if not recent:
        print("最近1週間のランニングアクティビティはありません。")
        return

    # Sort by ID descending to find newest
    recent_sorted = sorted(recent, key=lambda a: a.id, reverse=True)
    newest = recent_sorted[0]

    if newest.id <= last_id:
        print(f"新しいアクティビティはありません（最新ID: {newest.id}）。")
        return

    print(f"新しいアクティビティを検出: {newest.name} (ID: {newest.id})")

    # Fetch enriched streams for the new activity
    try:
        newest = client._enrich_with_streams(newest)
    except Exception:
        pass  # streams may not be ready immediately

    # Fetch 12 weeks for analysis context
    try:
        all_activities = client.fetch_activities(weeks=12)
    except Exception as e:
        print(f"WARNING: 12週分の取得に失敗、1週分で分析します: {e}", file=sys.stderr)
        all_activities = recent

    zones = TrainingZones(aet_hr=aet_hr, ant_hr=ant_hr)
    result = analyze(all_activities, zones)

    # Load races
    races = load_races()

    # Build activity summary for single-activity advice
    hr_info = f"平均心拍: {newest.average_heartrate:.0f}bpm" if newest.average_heartrate else "心拍データなし"
    activity_summary = (
        f"- 名前: {newest.name}\n"
        f"- 距離: {newest.distance_km:.1f}km\n"
        f"- 時間: {newest.moving_time_min:.0f}分\n"
        f"- {hr_info}\n"
        f"- 獲得標高: {newest.total_elevation_gain_m:.0f}m"
    )

    # Generate short advice
    try:
        advice = generate_single_activity_advice(activity_summary, result, races)
    except Exception as e:
        print(f"WARNING: AIアドバイス生成に失敗: {e}", file=sys.stderr)
        advice = "（アドバイスの生成に失敗しました）"

    # Send Discord notification
    sent = send_new_activity_notification(
        activity=newest,
        result=result,
        advice=advice,
        races=races if races else None,
    )

    if sent:
        print("Discord通知を送信しました。")
    else:
        print("Discord通知の送信をスキップしました。", file=sys.stderr)

    # Update state file (workflow will git commit & push this file)
    write_last_id(newest.id)
    print(f"NEW_ACTIVITY_ID={newest.id}")


if __name__ == "__main__":
    main()
