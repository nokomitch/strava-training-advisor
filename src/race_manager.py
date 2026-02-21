"""Race calendar management and training phase detection."""

import os
from datetime import date

import yaml

from .models import Race, RacePriority, TrainingPhase


def load_races(races_yaml_path: str | None = None) -> list[Race]:
    """Load races from races.yaml. Returns empty list if file not found."""
    if races_yaml_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        races_yaml_path = os.path.join(project_root, "races.yaml")

    if not os.path.exists(races_yaml_path):
        return []

    with open(races_yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    races = []
    for r in data.get("races", []):
        races.append(
            Race(
                name=r["name"],
                date=r["date"],  # PyYAML parses YYYY-MM-DD as date automatically
                priority=r["priority"],
                distance_km=float(r["distance_km"]),
                notes=r.get("notes", ""),
            )
        )
    return sorted(races, key=lambda r: r.date)


def get_upcoming_races(races: list[Race], days: int = 365) -> list[Race]:
    """Return races within the next N days, excluding past races."""
    return [r for r in races if 0 <= r.days_until <= days]


def get_next_a_race(races: list[Race]) -> Race | None:
    """Return the nearest upcoming A-priority race."""
    a_races = [r for r in races if r.priority == "A" and not r.is_past]
    return a_races[0] if a_races else None


def get_training_phase(races: list[Race]) -> tuple[TrainingPhase, Race | None]:
    """
    Determine the current training phase based on the nearest A-race.

    Returns:
        (phase, next_a_race) tuple. If no A-race, returns ("Base", None).
    """
    next_a = get_next_a_race(races)
    if next_a is None:
        return "Base", None

    days = next_a.days_until

    # Check if we just finished an A-race (within 2 weeks)
    past_a_races = [r for r in races if r.priority == "A" and r.is_past]
    if past_a_races:
        most_recent_past = max(past_a_races, key=lambda r: r.date)
        days_since = (date.today() - most_recent_past.date).days
        if days_since <= 14:
            return "Recovery", next_a

    if days > 84:      # >12 weeks
        return "Base", next_a
    elif days > 56:    # 8-12 weeks
        return "Build", next_a
    elif days > 28:    # 4-8 weeks
        return "Peak", next_a
    else:              # 0-4 weeks
        return "Taper", next_a


def format_race_context(races: list[Race]) -> str:
    """Format race information as a string for inclusion in AI prompts."""
    if not races:
        return "## レース予定\nレース予定はありません。\n"

    phase, next_a = get_training_phase(races)
    upcoming = get_upcoming_races(races, days=365)

    phase_descriptions = {
        "Base": "有酸素ベース構築期（低強度中心）",
        "Build": "ビルドアップ期（量・質の増加）",
        "Peak": "ピーク期（最大負荷）",
        "Taper": "テーパリング期（疲労抜き・レース準備）",
        "Recovery": "回復期（Aレース直後）",
    }

    lines = ["## レース予定"]

    if next_a:
        lines.append(
            f"- **次のAレース**: {next_a.name}（{next_a.date.strftime('%Y/%m/%d')}）"
            f" まで{next_a.days_until}日"
        )
    lines.append(f"- **現在のフェーズ**: {phase}（{phase_descriptions.get(phase, '')}）")

    if upcoming:
        lines.append("\n### 今後1年間のレース予定")
        for r in upcoming:
            priority_label = {"A": "🔴 Aレース", "B": "🟡 Bレース", "C": "🟢 Cレース"}[r.priority]
            lines.append(
                f"- {r.date.strftime('%m/%d')} {r.name} "
                f"({r.distance_km:.0f}km) [{priority_label}] まで{r.days_until}日"
                + (f" — {r.notes}" if r.notes else "")
            )

    return "\n".join(lines)
