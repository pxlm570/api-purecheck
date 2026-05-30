from __future__ import annotations

import argparse
import sys
from typing import Sequence

from api_purecheck import __version__
from api_purecheck.baseline import BaselineOptions, collect_baseline
from api_purecheck.batch import batch_dry_run, load_batch_configs, run_batch
from api_purecheck.config import AuditConfig, load_config
from api_purecheck.model_profiles import MODEL_PROFILES
from api_purecheck.models import model_examples
from api_purecheck.monitor import monitor_dry_run, run_monitor
from api_purecheck.report import emit_report
from api_purecheck.runner import RunOptions, dry_run_report, run_audit
from api_purecheck.web import serve_web


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="api-purecheck",
        description="轻量检测中转站 API 是否像它声称的模型。",
    )
    parser.add_argument("--version", action="version", version=f"api-purecheck {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="运行一次 API 纯度检测。")
    check.add_argument("--config", help="JSON 配置文件路径。")
    check.add_argument("--base-url", help="API base URL。")
    check.add_argument("--api-key", help="API key。输出和日志中会脱敏。")
    check.add_argument("--model", dest="claimed_model", help="中转站声称提供的模型名。")
    check.add_argument("--api-type", choices=["openai-compatible", "anthropic"], default=None, help="API 协议类型。")
    check.add_argument("--level", choices=["quick", "standard", "deep"], default=None, help="检测强度。")
    check.add_argument("--format", choices=["text", "json", "html", "markdown", "md"], default=None, help="输出格式。")
    check.add_argument("--output", help="写入报告文件。")
    check.add_argument("--timeout", type=float, default=None, help="单次请求超时时间，单位秒。")
    check.add_argument("--baseline-dir", default=None, help="模型基线目录。默认使用 baselines。")
    check.add_argument("--probe-file", default=None, help="自定义探针 JSON 文件。")
    check.add_argument("--dry-run", action="store_true", help="只校验配置，不发起真实 API 请求。")
    check.set_defaults(func=handle_check)

    serve = subparsers.add_parser("serve", help="启动本地 Web UI。")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址。")
    serve.add_argument("--port", type=int, default=8765, help="监听端口。")
    serve.set_defaults(func=handle_serve)

    calibrate = subparsers.add_parser("calibrate", help="采集可信模型基线。")
    calibrate.add_argument("--provider", required=True, help="基线 provider，例如 openai。")
    calibrate.add_argument("--base-url", required=True, help="可信 OpenAI-compatible API base URL。")
    calibrate.add_argument("--api-key", required=True, help="可信 API key。不会写入基线文件。")
    calibrate.add_argument("--model", required=True, help="基线模型名。")
    calibrate.add_argument("--api-type", choices=["openai-compatible", "anthropic"], default="openai-compatible", help="API 协议类型。")
    calibrate.add_argument("--level", choices=["quick", "standard", "deep"], default="standard", help="采集强度。")
    calibrate.add_argument("--timeout", type=float, default=60.0, help="单次请求超时时间，单位秒。")
    calibrate.add_argument("--output", required=True, help="基线输出路径。")
    calibrate.set_defaults(func=handle_calibrate)

    monitor = subparsers.add_parser("monitor", help="按配置重复检测并保存报告。")
    monitor.add_argument("--config", required=True, help="JSON 配置文件路径。")
    monitor.add_argument("--runs", type=int, default=1, help="检测次数。默认 1 次。")
    monitor.add_argument("--interval-seconds", type=float, default=3600.0, help="两次检测之间的间隔秒数。")
    monitor.add_argument("--output-dir", default="reports/monitor", help="监控报告输出目录。")
    monitor.add_argument("--dry-run", action="store_true", help="只预估请求数，不发起真实 API 请求。")
    monitor.set_defaults(func=handle_monitor)

    batch = subparsers.add_parser("batch", help="批量检测多个 API endpoint。")
    batch.add_argument("--file", required=True, help="批量 JSON 文件路径。")
    batch.add_argument("--output", help="写入 JSON 报告文件。")
    batch.add_argument("--dry-run", action="store_true", help="只预估请求数，不发起真实 API 请求。")
    batch.set_defaults(func=handle_batch)

    models = subparsers.add_parser("models", help="列出常见模型名示例。")
    models.add_argument(
        "--provider",
        choices=["openai", "anthropic", "gpt", "claude", "deepseek", "kimi", "glm", "minimax"],
        default=None,
        help="按 provider / 模型族过滤。",
    )
    models.set_defaults(func=handle_models)

    profiles = subparsers.add_parser("profiles", help="列出内置模型族画像。")
    profiles.set_defaults(func=handle_profiles)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2


def handle_check(args: argparse.Namespace) -> int:
    config = _merge_check_config(args)
    config.validate()

    if args.dry_run:
        report = dry_run_report(config)
    else:
        report = run_audit(config, RunOptions(timeout_seconds=config.timeout_seconds))

    emit_report(report, config.output_format, args.output)
    return 0


def handle_serve(args: argparse.Namespace) -> int:
    serve_web(args.host, args.port)
    return 0


def handle_calibrate(args: argparse.Namespace) -> int:
    config = AuditConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        claimed_model=args.model,
        level=args.level,
        output_format="json",
        timeout_seconds=args.timeout,
        api_type=args.api_type,
    )
    config.validate()
    report = collect_baseline(config, BaselineOptions(provider=args.provider, output=args.output))
    emit_report(report, "json", None)
    return 0


def handle_monitor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate()
    if args.dry_run:
        report = monitor_dry_run(
            config,
            runs=args.runs,
            interval_seconds=args.interval_seconds,
            output_dir=args.output_dir,
        )
    else:
        report = run_monitor(
            config,
            runs=args.runs,
            interval_seconds=args.interval_seconds,
            output_dir=args.output_dir,
        )
    emit_report(report, "json", None)
    return 0


def handle_batch(args: argparse.Namespace) -> int:
    configs = load_batch_configs(args.file)
    report = batch_dry_run(configs) if args.dry_run else run_batch(configs)
    emit_report(report, "json", args.output)
    return 0


def handle_models(args: argparse.Namespace) -> int:
    items = model_examples(args.provider)
    print("常见模型名示例：")
    for item in items:
        print(f"- {item.provider}: {item.model} ({item.note})")
    print("\n说明：这只是示例列表。中转站模型名可能不同，检测时可以输入任意模型名。")
    return 0


def handle_profiles(args: argparse.Namespace) -> int:
    print("内置模型族画像：")
    for profile in MODEL_PROFILES:
        print(f"- {profile.display_name} ({profile.family})")
        print(f"  API 类型：{', '.join(profile.api_types)}")
        print(f"  常见模型名：{', '.join(profile.model_names)}")
        print(f"  说明：{profile.notes}")
    return 0


def _merge_check_config(args: argparse.Namespace) -> AuditConfig:
    base = load_config(args.config) if args.config else AuditConfig(base_url="", api_key="", claimed_model="")
    return AuditConfig(
        base_url=args.base_url or base.base_url,
        api_key=args.api_key or base.api_key,
        claimed_model=args.claimed_model or base.claimed_model,
        level=args.level or base.level,
        output_format=args.format or base.output_format,
        timeout_seconds=args.timeout or base.timeout_seconds,
        baseline_dir=args.baseline_dir or base.baseline_dir,
        api_type=args.api_type or base.api_type,
        probe_file=args.probe_file or base.probe_file,
    )
