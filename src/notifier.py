"""Discord Webhook notification for new Strava activities."""

import os

import requests

from .models import Activity, AnalysisResult, Race, WeeklyStats
from .race_manager import get_next_a_race, get_training_phase


def _zone_color(low_intensity_pct: float) -> int:
    """Return Discord embed color based on low-intensity percentage."""
    if low_intensity_pct >= 85:
        return 0x2ECC71
    elif low_intensity_pct >= 70:
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
        intensity_icon = "✅" if low_pct >= 85 else "⚠️" if low_pct >= 70 else "🔴"
        intensity_str = f"{low_pct:.0f}% {intensity_icon}（目標85%以上）"
    else:
        zone_str = "心拍データなし"
        intensity_str = "—"

    # HR info
    hr_str = f"{activity.average_heartrate:.0f} bpm" if activity.average_heartrate else "データなし"

    # Heart rate drift info
    drift_str = ""
    if activity.hr_drift_pct is not None:
        drift_icon = "✅" if activity.hr_drift_pct <= 3 else "⚠️" if activity.hr_drift_pct <= 5 else "🔴"
        drift_str = f"\n💗 心拍ドリフト: {activity.hr_drift_pct:+.1f}% {drift_icon}"
        if activity.hr_drift_pct > 10:
            drift_str += "（深刻→強度過多）"
        elif activity.hr_drift_pct > 5:
            drift_str += "（有酸素ベース不足の可能性）"

    # Activity-level zone distribution
    act_zone_str = ""
    if activity.zone_distribution and activity.zone_distribution.total_s > 0:
        azd = activity.zone_distribution
        act_low = azd.low_intensity_pct
        act_icon = "✅" if act_low >= 80 else "⚠️" if act_low >= 65 else "🔴"
        act_zone_str = (
            f"\nこのラン: Z1:{azd.zone_pct(1):.0f}% Z2:{azd.zone_pct(2):.0f}%"
            f" Z3:{azd.zone_pct(3):.0f}% Z4:{azd.zone_pct(4):.0f}%"
            f" (低強度{act_low:.0f}% {act_icon})"
        )

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
                    + drift_str
                    + act_zone_str
                ),
                "inline": False,
            },
            {
                "name": "📈 Uphill Athlete ゾーン分布（過去12週累計）",
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


def send_weekly_summary(
    current_week: WeeklyStats,
    result: AnalysisResult,
    advice: str,
    races: list[Race] | None = None,
    training_phase: str = "Base",
    webhook_url: str | None = None,
) -> bool:
    """Send a weekly training summary to Discord.

    Returns True if the message was sent successfully.
    """
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not url:
        print("DISCORD_WEBHOOK_URL が設定されていません。通知をスキップします。")
        return False

    zd = current_week.zone_distribution
    low_pct = zd.low_intensity_pct if zd.total_s > 0 else 0.0
    has_zone_data = zd.total_s > 0

    # ゾーン分布文字列
    if has_zone_data:
        zone_str = (
            f"Z1: {zd.zone_pct(1):.0f}% / Z2: {zd.zone_pct(2):.0f}% / "
            f"Z3: {zd.zone_pct(3):.0f}% / Z4: {zd.zone_pct(4):.0f}%"
        )
        intensity_icon = "✅" if low_pct >= 80 else "⚠️" if low_pct >= 65 else "🔴"
        intensity_str = f"{low_pct:.0f}% {intensity_icon}（目標80%以上）"
    else:
        zone_str = "心拍データなし"
        intensity_str = "—"

    # 週間実績
    week_label = current_week.week_start.strftime("%m/%d")
    stats_value = (
        f"📏 **{current_week.total_distance_km:.1f} km** "
        f"| ⏱ **{current_week.total_time_h:.1f} 時間** "
        f"| 🏃 **{current_week.activity_count} 回**\n"
        f"{zone_str}\n低強度割合: {intensity_str}"
    )

    # 3:1サイクル評価
    overall_dist = result.overall_zone_distribution
    overall_low_pct = overall_dist.low_intensity_pct if overall_dist.total_s > 0 else 0.0
    cycle_value = (
        f"{'✅ 3:1サイクル実践中' if result.is_recovery_week_pattern else '⚠️ 回復週パターンなし（計画的な回復週を導入してください）'}\n"
        f"12週平均: {result.avg_weekly_km:.1f} km/週 / {result.avg_weekly_h:.1f} h/週\n"
        f"12週全体の低強度割合: {overall_low_pct:.0f}%"
    )

    # レース・フェーズ情報
    next_a_race = get_next_a_race(races) if races else None
    phase_descriptions = {
        "Base": "有酸素ベース構築期",
        "Build": "ビルドアップ期",
        "Peak": "ピーク期",
        "Taper": "テーパリング期",
        "Recovery": "回復期",
    }
    phase_str = f"**{training_phase}**（{phase_descriptions.get(training_phase, '')}）"
    race_value = phase_str
    if next_a_race:
        race_value += f"\n🎯 次のAレース: **{next_a_race.name}** まで **{next_a_race.days_until}日**"

    # Truncate advice for embed (600文字制限)
    short_advice = advice[:600] + "..." if len(advice) > 600 else advice

    embed = {
        "title": f"📅 週次トレーニングサマリー（{week_label}週）",
        "color": _zone_color(low_pct) if has_zone_data else 0x95A5A6,
        "fields": [
            {
                "name": "📊 今週の実績",
                "value": stats_value,
                "inline": False,
            },
            {
                "name": "🔄 3:1サイクル評価",
                "value": cycle_value,
                "inline": False,
            },
            {
                "name": "🏁 フェーズ・レース情報",
                "value": race_value,
                "inline": False,
            },
            {
                "name": "🤖 AIコーチのアドバイス（来週の目標・スケジュール）",
                "value": short_advice,
                "inline": False,
            },
        ],
        "footer": {
            "text": "Strava Training Advisor | Weekly Summary | Uphill Athlete methodology"
        },
    }

    payload = {"embeds": [embed]}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"週次サマリーのDiscord通知送信に失敗しました: {e}")
        return False

def send_strength_activity_notification(
    activity: Activity,
    result: AnalysisResult,
    athlete_profile=None,
    webhook_url: str | None = None,
) -> bool:
    """筋トレアクティビティの Discord 通知を送る。"""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not url:
        return False

    target = athlete_profile.strength_target_per_week if athlete_profile else 2
    last_week_strength = result.strength_counts_per_week[-1] if result.strength_counts_per_week else 0
    status = "✅ 今週の目標達成！" if last_week_strength >= target else f"今週 {last_week_strength}/{target}回"

    h = activity.moving_time_s // 3600
    m = (activity.moving_time_s % 3600) // 60
    duration = f"{h}時間{m:02d}分" if h > 0 else f"{m}分"

    embed = {
        "title": f"💪 {activity.name}",
        "url": f"https://www.strava.com/activities/{activity.id}",
        "color": 0x3498DB,
        "fields": [{"name": "筋トレ記録", "value": f"⏱ {duration} | {status}", "inline": False}],
        "footer": {"text": "Strava Training Advisor"},
    }
    try:
        resp = requests.post(url, json={"embeds": [embed]}, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Discord通知の送信に失敗しました: {e}")
        return False