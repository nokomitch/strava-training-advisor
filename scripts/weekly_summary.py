#!/usr/bin/env python3
"""
Weekly training summary generator for GitHub Actions.

毎週日曜日 JST 20:00 に GitHub Actions から実行され、
その週のトレーニング実績を振り返り、来週の目標をDiscordへ送信する。

Usage:
    uv run python scripts/weekly_summary.py

Output (stdout, parsed by workflow):
    WEEKLY_SUMMARY_SENT=true   (送信成功時)
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.advisor import generate_weekly_summary_advice
from src.analyzer import analyze
from src.models import TrainingZones, WeeklyStats, ZoneDistribution
from src.notifier import send_weekly_summary
from src.race_manager import get_training_phase, load_races
from src.strava_client import StravaClient

_JST = ZoneInfo("Asia/Tokyo")


def get_current_week_stats(result, this_week_monday: datetime) -> WeeklyStats:
    """今週（JST月曜始まり）のWeeklyStatsをresult.weeksから取得する。
    見つからない場合は空のWeeklyStatsを返す。"""
    for ws in result.weeks:
        if ws.week_start.date() == this_week_monday.date():
            return ws
    # 今週のアクティビティがない場合
    return WeeklyStats(
        week_start=this_week_monday,
        activities=[],
        zone_distribution=ZoneDistribution(),
    )


def main() -> None:
    aet_hr = int(os.getenv("ATHLETE_AET_HR", "150"))
    ant_hr = int(os.getenv("ATHLETE_ANT_HR", "170"))

    now_jst = datetime.now(_JST)
    print(f"実行時刻（JST）: {now_jst.strftime('%Y-%m-%d %H:%M %Z')}")

    # 今週の月曜日（JST）を計算
    today_jst = now_jst.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    this_week_monday = today_jst - timedelta(days=today_jst.weekday())
    print(f"今週の開始（月曜）: {this_week_monday.strftime('%Y-%m-%d')}")

    client = StravaClient()

    # 12週分のアクティビティを取得
    try:
        all_activities = client.fetch_activities(weeks=12)
    except Exception as e:
        print(f"ERROR: Strava APIからのデータ取得に失敗: {e}", file=sys.stderr)
        sys.exit(1)

    if not all_activities:
        print("過去12週間のランニングアクティビティはありません。週次サマリーをスキップします。")
        return

    zones = TrainingZones(aet_hr=aet_hr, ant_hr=ant_hr)
    result = analyze(all_activities, zones)

    # レース情報とトレーニングフェーズ
    races = load_races()
    training_phase, next_a_race = get_training_phase(races)

    # 今週のWeeklyStats取得
    current_week = get_current_week_stats(result, this_week_monday)
    print(
        f"今週の実績: {current_week.total_distance_km:.1f}km / "
        f"{current_week.total_time_h:.1f}h / {current_week.activity_count}回"
    )

    # AIによる週次サマリーアドバイス生成
    print("週次サマリーアドバイスを生成中...")
    try:
        advice = generate_weekly_summary_advice(
            result=result,
            current_week=current_week,
            races=races if races else None,
            training_phase=training_phase,
        )
    except Exception as e:
        print(f"WARNING: AIアドバイス生成に失敗: {e}", file=sys.stderr)
        advice = "（アドバイスの生成に失敗しました）"

    # Discord送信
    sent = send_weekly_summary(
        current_week=current_week,
        result=result,
        advice=advice,
        races=races if races else None,
        training_phase=training_phase,
    )

    if sent:
        print("週次サマリーをDiscordに送信しました。")
        print("WEEKLY_SUMMARY_SENT=true")
    else:
        print("週次サマリーの送信をスキップしました。", file=sys.stderr)


if __name__ == "__main__":
    main()
