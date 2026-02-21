"""Discord Webhook notification for new Strava activities."""

import os

import requests

from .models import Activity, AnalysisResult, Race
from .race_manager import get_next_a_race


def _zone_color(low_intensity_pct: float) -> int:
    """Return Discord embed color based on low-intensity percentage."""
    if low_intensity_pct >= 80:
        return 0x2ECC71  # Green - on target
    elif low_intensity_pct >= 65:
        return 0xF39C12  # Orange - slightly high intensity
    else:
        return 0xE74C3C  # Red - too much high intensity


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}時間{m:02d}分"
    return f"{m}分"


def send_new_activity_notification(
    activity: Activity,
    result: AnalysisResult,
    advice: str,
    races: list[Race] | None = None,
    webhook_url: str | None = None,
) -> bool:
    """
    Send a Discord notification for a new activity.

    Returns True if the message was sent successfully.
    """
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not url:
        print("DISCORD_WEBHOOK_URL が設定されていません。通知をスキップします。")
        return False

    dist = result.overall_zone_distribution
    zones = result.zones
    low_pct = dist.low_intensity_pct
    has_hr = dist.total_s > 0

    # Build zone distribution string
    if has_hr:
        zone_str = (
            f"Z1: {dist.zone_pct(1):.0f}% / "
            f"Z2: {dist.zone_pct(2):.0f}% / "
            f"Z3: {dist.zone_pct(3):.0f}% / "
            f"Z4: {dist.zone_pct(4):.0f}%"
        )
        intensity_icon = "✅" if low_pct >= 80 else "⚠️" if low_pct >= 65 else "🔴"
        intensity_str = f"{low_pct:.0f}% {intensity_icon}（目標80%以上）"
    else:
        zone_str = "心拍データなし"
        intensity_str = "—"

    # HR info
    hr_str = f"{activity.average_heartrate:.0f} bpm" if activity.average_heartrate else "データなし"

    # Race info
    next_a_race = get_next_a_race(races) if races else None
    race_str = (
        f"🎯 **次のAレース**: {next_a_race.name} まで **{next_a_race.days_until}日**"
        if next_a_race
        else ""
    )

    # Strava activity link
    strava_url = f"https://www.strava.com/activities/{activity.id}"

    # Truncate advice for embed
    short_advice = advice[:800] + "..." if len(advice) > 800 else advice

    embed = {
        "title": f"🏃 {activity.name}",
        "url": strava_url,
        "color": _zone_color(low_pct) if has_hr else 0x95A5A6,
        "fields": [
            {
                "name": "📊 アクティビティ",
                "value": (
                    f"📏 **{activity.distance_km:.1f} km** "
                    f"| ⏱ **{_format_duration(activity.moving_time_s)}** "
                    f"| 💓 **{hr_str}**"
                    + (f"\n🏔 獲得標高: {activity.total_elevation_gain_m:.0f}m" if activity.total_elevation_gain_m > 0 else "")
                ),
                "inline": False,
            },
            {
                "name": "📈 Uphill Athlete ゾーン分布（過去12週）",
                "value": f"{zone_str}\n低強度割合: {intensity_str}",
                "inline": False,
            },
            {
                "name": "🤖 AIコーチのフィードバック",
                "value": short_advice,
                "inline": False,
            },
        ],
        "footer": {
            "text": "Strava Training Advisor | Uphill Athlete methodology"
        },
    }

    if race_str:
        embed["fields"].insert(2, {"name": "🏁 レース目標", "value": race_str, "inline": False})

    payload = {"embeds": [embed]}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Discord通知の送信に失敗しました: {e}")
        return False
