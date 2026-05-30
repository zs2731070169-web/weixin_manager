"""命令行入口。

用法示例::

    python -m official_account_cancel                 # 正式运行
    python -m official_account_cancel --dry-run       # 只识别不点击（联调用）
    python -m official_account_cancel --max 20        # 最多取消 20 个
    python -m official_account_cancel --confidence 0.8 -v
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
import time
from pathlib import Path

from . import __version__
from .config import Settings, load_settings
from .gui import GuiAutomationError, GuiController
from .workflow import UnsubscribeWorkflow


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="official_account_cancel",
        description="批量取消关注 macOS 微信桌面客户端中的公众号。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="自定义 YAML 配置文件路径（默认使用包内的 config.yml）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="只做图像识别与日志输出，不实际点击/输入",
    )
    p.add_argument(
        "--max",
        dest="max_iterations",
        type=int,
        default=None,
        metavar="N",
        help="最多处理多少个公众号（默认使用配置中的安全上限）",
    )
    p.add_argument(
        "--confidence",
        type=float,
        default=None,
        metavar="0~1",
        help="图像匹配置信度，越大越严格",
    )
    p.add_argument(
        "--countdown",
        type=float,
        default=None,
        metavar="SEC",
        help="正式开始前的倒计时秒数",
    )
    p.add_argument(
        "--no-failsafe",
        action="store_true",
        help="关闭 pyautogui 急停（不建议）",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出 DEBUG 级日志",
    )
    return p


def _build_settings(args: argparse.Namespace) -> Settings:
    """先从 TOML 配置文件加载，再用命令行参数覆盖（frozen dataclass 用 replace）。"""
    base = load_settings(args.config)
    overrides: dict = {"dry_run": args.dry_run}
    if args.max_iterations is not None:
        overrides["max_iterations"] = args.max_iterations
    if args.confidence is not None:
        overrides["confidence"] = args.confidence
    if args.countdown is not None:
        overrides["start_countdown"] = args.countdown
    if args.no_failsafe:
        overrides["failsafe"] = False
    return dataclasses.replace(base, **overrides)


def _countdown(seconds: float) -> None:
    """开始前倒计时，给用户把鼠标移开 / 切到微信的时间。"""
    remaining = int(seconds)
    for i in range(remaining, 0, -1):
        print(f"\r{i} 秒后开始……（Ctrl+C 取消）", end="", flush=True)
        time.sleep(1)
    print("\r开始！" + " " * 20)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = _build_settings(args)

    if not settings.assets_dir.exists():
        print(f"错误：找不到模板图片目录 {settings.assets_dir}", file=sys.stderr)
        return 2

    if settings.dry_run:
        print("【DRY-RUN】仅识别不操作。")

    try:
        if settings.start_countdown > 0:
            _countdown(settings.start_countdown)

        gui = GuiController(
            confidence=settings.confidence,
            grayscale=settings.grayscale,
            dry_run=settings.dry_run,
            failsafe=settings.failsafe,
        )
        stats = UnsubscribeWorkflow(settings, gui).run()
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130
    except GuiAutomationError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"\n完成：成功取消 {stats.processed} 个"
        f"（正常分支 {stats.normal_branch} / 失败分支 {stats.fail_branch}）。"
        f"\n终止原因：{stats.stopped_reason}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
