#!/usr/bin/env python3
"""
Main entry point for Strava Training Advisor.

Fetches running activities from Strava, analyzes them using
Uphill Athlete principles, generates AI advice, and creates
an HTML report.

Usage:
    uv run python scripts/run_advisor.py [--weeks N]
"""

import argparse
import os
import subprocess
import sys

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import analyze
from src.advisor import generate_advice
from src.models import TrainingZones
from src.report import generate_report
from src.strava_client import StravaClient

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strava Training Advisor")
    parser.add_argument(
        "--weeks",
        type=int,
        default=12,
        help="Number of weeks to analyze (default: 12)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip HTML report generation",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open HTML report in browser after generation",
    )
    return parser.parse_args()


def load_training_zones() -> TrainingZones:
    """Load AeT and AnT from environment variables."""
    from dotenv import load_dotenv
    load_dotenv()

    aet_hr = int(os.getenv("ATHLETE_AET_HR", "0"))
    ant_hr = int(os.getenv("ATHLETE_ANT_HR", "0"))

    if aet_hr == 0 or ant_hr == 0:
        console.print(
            Panel(
                "[yellow]⚠️  AeT/AnT 心拍数が設定されていません。\n\n"
                ".env ファイルに以下を追加してください：\n"
                "  ATHLETE_AET_HR=150  # 有酸素閾値心拍数\n"
                "  ATHLETE_ANT_HR=170  # 無酸素閾値心拍数\n\n"
                "参考: Uphill Athleteの心拍ドリフトテストで測定できます。\n"
                "https://uphillathlete.com/aerobic-training/heart-rate-drift-test/[/yellow]",
                title="設定が必要です",
                border_style="yellow",
            )
        )
        # Use fallback estimates
        console.print("[dim]年齢ベースの推定値でデフォルト設定します（不正確な場合があります）[/dim]")
        aet_hr = 150
        ant_hr = 170

    return TrainingZones(aet_hr=aet_hr, ant_hr=ant_hr)


def print_summary(result: "AnalysisResult", zones: TrainingZones) -> None:  # noqa: F821
    """Print analysis summary to terminal."""
    console.print("\n")
    console.print(
        Panel(
            f"[bold]集計期間:[/bold] 過去 {len(result.weeks)} 週間  |  "
            f"[bold]アクティビティ数:[/bold] {result.total_activities}  |  "
            f"[bold]平均週間距離:[/bold] {result.avg_weekly_km:.1f} km  |  "
            f"[bold]平均週間時間:[/bold] {result.avg_weekly_h:.1f} h",
            title="[bold red]トレーニングサマリー[/bold red]",
            border_style="red",
        )
    )

    # Zone distribution table
    dist = result.overall_zone_distribution
    if dist.total_s > 0:
        table = Table(title="ゾーン強度分布", show_header=True, header_style="bold cyan")
        table.add_column("ゾーン", style="bold")
        table.add_column("心拍範囲", justify="right")
        table.add_column("時間", justify="right")
        table.add_column("割合", justify="right")

        z_data = [
            ("Zone 1 (非常に楽)", f"{zones.zone1_min:.0f}–{zones.zone1_max:.0f} bpm", dist.zone1_s, dist.zone_pct(1)),
            ("Zone 2 (楽〜中程度)", f"{zones.zone2_min:.0f}–{zones.zone2_max:.0f} bpm", dist.zone2_s, dist.zone_pct(2)),
            ("Zone 3 (中〜ハード)", f"{zones.zone3_min:.0f}–{zones.zone3_max:.0f} bpm", dist.zone3_s, dist.zone_pct(3)),
            ("Zone 4 (非常にハード)", f"{zones.zone4_min:.0f}+ bpm", dist.zone4_s, dist.zone_pct(4)),
        ]
        for name, hr_range, secs, pct in z_data:
            table.add_row(name, hr_range, f"{secs/3600:.1f}h", f"{pct:.1f}%")

        console.print(table)

        low_pct = dist.low_intensity_pct
        color = "green" if low_pct >= 80 else "yellow" if low_pct >= 65 else "red"
        console.print(
            f"\n  低強度(Z1+Z2): [{color}]{low_pct:.1f}%[/{color}] "
            f"(目標: 80%以上) | "
            f"回復週パターン: {'✅ あり' if result.is_recovery_week_pattern else '❌ なし'}"
        )
    else:
        console.print("[dim]  心拍データがないためゾーン分布を表示できません[/dim]")


def main() -> None:
    args = parse_args()

    console.print(
        Panel(
            "[bold]Strava Training Advisor[/bold]\nPowered by Uphill Athlete methodology & Claude AI",
            border_style="red",
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # 1. Load zones
        task = progress.add_task("トレーニングゾーンを読み込み中...", total=None)
        zones = load_training_zones()
        progress.update(task, description=f"ゾーン設定: AeT={zones.aet_hr}bpm / AnT={zones.ant_hr}bpm ✅")
        progress.stop_task(task)

        # 2. Fetch activities
        task2 = progress.add_task(f"Stravaからアクティビティを取得中（過去{args.weeks}週）...", total=None)
        try:
            client = StravaClient()
            activities = client.fetch_activities(weeks=args.weeks)
        except ValueError as e:
            progress.stop()
            console.print(f"\n[red]ERROR: {e}[/red]")
            console.print("まず setup_oauth.py を実行してください：")
            console.print("  [bold]uv run python scripts/setup_oauth.py[/bold]")
            sys.exit(1)
        progress.update(task2, description=f"{len(activities)}件のランニングアクティビティを取得 ✅")
        progress.stop_task(task2)

        if not activities:
            progress.stop()
            console.print(f"\n[yellow]過去{args.weeks}週間のランニングアクティビティが見つかりませんでした。[/yellow]")
            sys.exit(0)

        # 3. Analyze
        task3 = progress.add_task("Uphill Athlete原則で分析中...", total=None)
        result = analyze(activities, zones)
        progress.update(task3, description="分析完了 ✅")
        progress.stop_task(task3)

        # 4. Generate AI advice
        task4 = progress.add_task("AIトレーニングアドバイスを生成中...", total=None)
        advice = generate_advice(result)
        progress.update(task4, description="アドバイス生成完了 ✅")
        progress.stop_task(task4)

        # 5. Generate report
        report_path = None
        if not args.no_report:
            task5 = progress.add_task("HTMLレポートを生成中...", total=None)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            report_path = generate_report(result, advice, os.path.join(project_root, "results"))
            progress.update(task5, description=f"レポート生成完了 ✅")
            progress.stop_task(task5)

    # Print summary
    print_summary(result, zones)

    # Print advice
    console.print("\n")
    console.print(Panel(advice, title="[bold]AIトレーニングアドバイス[/bold]", border_style="cyan"))

    # Report location
    if report_path:
        console.print(f"\n[dim]HTMLレポート: {report_path}[/dim]")
        if args.open:
            subprocess.run(["open", report_path], check=False)


if __name__ == "__main__":
    main()
