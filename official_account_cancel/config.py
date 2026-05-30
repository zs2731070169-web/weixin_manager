"""配置加载。

可调参数全部外置到同目录下的 [`config.yml`](config.yml)，本模块负责在启动时
读取并解析成强类型的 :class:`Settings` / :class:`Timings` 实例。

之所以保留 dataclass 定义（而非直接传字典）：保留字段类型提示与 IDE 补全，
并在 ``config.yml`` 缺失时仍能回退到内置默认值。

所有时长单位均为秒。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# 项目根目录（…/weixin_manager），assets 与 official_account_cancel 包同级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ASSETS_DIR = _PROJECT_ROOT / "assets"

# 默认配置文件：与本模块同目录的 config.yml
_DEFAULT_CONFIG_FILE = Path(__file__).resolve().parent / "config.yml"


@dataclass(frozen=True)
class Timings:
    """各步骤之间的等待时长，逐一对应原宏中的 Pause 动作。"""

    after_activate: float = 0.5      # 等待微信激活
    after_open_search: float = 1.0   # 按下 Cmd+F 后等待搜索框
    after_type_keyword: float = 1.0  # 输入关键字后等待搜索结果
    after_click_result: float = 0.5  # 点击搜索结果后
    after_click_account: float = 1.0 # 点击公众号后等待详情页
    after_click_following: float = 0.5  # 点击「已关注」后等待菜单
    after_branch_decision: float = 0.5  # 分支判定后

    # 正常分支：取消关注 -> 确认 -> 确认 -> 确认 -> Esc
    normal_between_clicks: float = 0.5
    normal_after_escape: float = 0.3

    # 失败分支：确认 -> (长等待) -> 确认 -> 确认 -> Esc
    fail_after_first_confirm: float = 2.5
    fail_between_clicks: float = 0.5
    fail_after_escape: float = 0.3


@dataclass(frozen=True)
class Settings:
    """运行期总配置。字段默认值仅作为 config.yml 缺失时的兜底。"""

    # —— 目标应用 ——
    wechat_bundle_id: str = "com.tencent.xinWeChat"
    wechat_app_name: str = "微信"

    # —— 资源 ——
    assets_dir: Path = _DEFAULT_ASSETS_DIR

    # —— 搜索 ——
    search_keyword: str = "公众号"

    # —— 图像匹配 ——
    confidence: float = 0.85
    search_result_confidence: float = 0.72
    grayscale: bool = True

    # —— 点击偏移 ——
    first_account_click_offset_y: int = 60

    # —— 安全 / 节流 ——
    max_iterations: int = 500
    start_countdown: float = 3.0
    failsafe: bool = True
    dry_run: bool = False

    timings: Timings = field(default_factory=Timings)

    # —— 模板图片文件名 ——
    img_search_result: str = "search_result_gzh.png"
    img_first_account: str = "first_account.png"
    img_following_button: str = "following_button.png"
    img_branch_marker: str = "branch_marker.png"   # 与「取消关注」同图，用于分支判定
    img_normal_unfollow: str = "normal_unfollow.png"
    img_normal_confirm_1: str = "normal_confirm_1.png"
    img_normal_confirm_2: str = "normal_confirm_2.png"
    img_normal_confirm_3: str = "normal_confirm_3.png"
    img_fail_confirm_1: str = "fail_confirm_1.png"
    img_fail_confirm_2: str = "fail_confirm_2.png"
    img_fail_confirm_3: str = "fail_confirm_3.png"

    def asset(self, filename: str) -> Path:
        """返回 assets 目录下某资源的绝对路径。"""
        return self.assets_dir / filename


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """从 YAML 配置文件加载 :class:`Settings`。

    Args:
        config_path: 配置文件路径；默认使用同目录的 ``config.yml``。

    Returns:
        解析得到的 :class:`Settings`。文件不存在时返回全内置默认值的实例。

    Raises:
        ValueError: 配置文件存在但解析失败（语法错误或字段不匹配）。
    """
    path = config_path or _DEFAULT_CONFIG_FILE
    if not path.exists():
        # 文件缺失不报错，回退到 dataclass 内置默认，保证可运行
        return Settings()

    try:
        with open(path, "r", encoding="utf-8") as fp:
            raw = yaml.safe_load(fp) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"配置文件解析失败 {path}: {exc}") from exc

    # 拆出嵌套段落
    timings_raw = raw.pop("timings", {})
    images_raw = raw.pop("images", {})

    # assets_dir 允许在 toml 里以字符串覆盖，否则用计算出的默认目录
    if "assets_dir" in raw:
        raw["assets_dir"] = Path(raw["assets_dir"]).expanduser()

    # [images] 下的键加上 img_ 前缀映射到 Settings 字段
    image_kwargs = {f"img_{key}": value for key, value in images_raw.items()}

    try:
        return Settings(timings=Timings(**timings_raw), **raw, **image_kwargs)
    except TypeError as exc:
        raise ValueError(f"配置文件字段与 Settings 不匹配 {path}: {exc}") from exc
