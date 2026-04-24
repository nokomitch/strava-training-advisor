"""Athlete profile loading and formatting for personalized AI advice."""

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class AthleteProfile:
    weekday_pattern: str = "平日: easy run"
    weekend_pattern: str = "週末: ロング走"
    strength_target_per_week: int = 2
    strength_notes: str = ""
    terrain_preference: str = "mixed"
    weekly_build_rate_max: int = 10
    recovery_week_interval: int = 4
    warmup_minutes: int = 10
    primary_goal: str = ""
    secondary_goal: str = ""
    weaknesses: list[str] = field(default_factory=list)


def load_athlete_profile(yaml_path: str | None = None) -> AthleteProfile | None:
    """athlete_profile.yaml を読み込む。ファイルがなければ None を返す（後方互換）。"""
    if yaml_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yaml_path = os.path.join(project_root, "athlete_profile.yaml")

    if not os.path.exists(yaml_path):
        return None

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    schedule = data.get("schedule", {})
    strength = schedule.get("strength_training", {})
    prefs = data.get("preferences", {})
    goals = data.get("goals", {})

    return AthleteProfile(
        weekday_pattern=schedule.get("weekday_pattern", "平日: easy run"),
        weekend_pattern=schedule.get("weekend_pattern", "週末: ロング走"),
        strength_target_per_week=int(strength.get("target_per_week", 2)),
        strength_notes=strength.get("notes", ""),
        terrain_preference=prefs.get("terrain", "mixed"),
        weekly_build_rate_max=int(prefs.get("weekly_build_rate_max", 10)),
        recovery_week_interval=int(prefs.get("recovery_week_interval", 4)),
        warmup_minutes=int(schedule.get("warmup_minutes", 10)),
        primary_goal=goals.get("primary", ""),
        secondary_goal=goals.get("secondary", ""),
        weaknesses=goals.get("weaknesses", []),
    )


def format_athlete_context(profile: AthleteProfile) -> str:
    """プロンプト用のアスリートプロファイルセクションを生成する。"""
    lines = ["## アスリートプロファイル"]
    lines.append(f"- 平日の練習: {profile.weekday_pattern}")
    lines.append(f"- 週末の練習: {profile.weekend_pattern}")
    lines.append(
        f"- 筋トレ目標: 週{profile.strength_target_per_week}回"
        + (f"（{profile.strength_notes}）" if profile.strength_notes else "")
    )
    lines.append(f"- 地形の好み: {profile.terrain_preference}")
    lines.append(f"- 週間ビルドレート上限: {profile.weekly_build_rate_max}%")
    lines.append(f"- 回復週サイクル: {profile.recovery_week_interval}週ごと")
    if profile.primary_goal:
        lines.append(f"- 主目標: {profile.primary_goal}")
    if profile.secondary_goal:
        lines.append(f"- 副目標: {profile.secondary_goal}")
    if profile.weaknesses:
        lines.append("- 課題・弱点:")
        for w in profile.weaknesses:
            lines.append(f"  - {w}")
    return "\n".join(lines)
