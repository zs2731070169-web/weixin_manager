"""GUI 自动化薄封装。

对 :mod:`pyautogui` 做一层语义化封装，把原宏中的 ActivateApplication、
MouseMoveAndClick(Relative=Image)、SimulateKeystroke、InsertText 等动作映射成
易读、可测试的方法，并统一处理「图片找不到」「dry-run」「日志」等横切关注点。

依赖：pyautogui + opencv-python（confidence 参数需要）+ pillow。
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# pyautogui 在 import 时即尝试连接显示服务，放到函数内部 import 可让单元测试
# 在无显示环境下也能导入本模块。
try:  # pragma: no cover - 取决于运行环境
    import pyautogui
    from pyautogui import ImageNotFoundException
except Exception:  # pragma: no cover
    pyautogui = None  # type: ignore[assignment]

    class ImageNotFoundException(Exception):  # type: ignore[no-redef]
        """pyautogui 不可用时的占位异常。"""


Point = Tuple[int, int]


class GuiAutomationError(RuntimeError):
    """GUI 自动化相关的统一异常基类。"""


class GuiController:
    """封装一次自动化会话所需的全部底层操作。"""

    def __init__(
        self,
        *,
        confidence: float = 0.85,
        grayscale: bool = True,
        dry_run: bool = False,
        failsafe: bool = True,
    ) -> None:
        if pyautogui is None:  # pragma: no cover
            raise GuiAutomationError(
                "未能导入 pyautogui，请先安装依赖：pip install -r requirements.txt"
            )
        self.confidence = confidence
        self.grayscale = grayscale
        self.dry_run = dry_run
        pyautogui.FAILSAFE = failsafe
        # 关闭 pyautogui 每个动作后的默认 0.1s 停顿，等待时长完全由我们显式控制
        pyautogui.PAUSE = 0.0

        # —— Retina 缩放系数 ——
        # pyautogui 在物理像素截图上定位（如 2880x1800），返回的是物理坐标；
        # 而 pyautogui.click 接受的是逻辑坐标（如 1440x900）。二者在 Retina(2x)
        # 屏上差一个缩放倍数，必须把定位坐标除以该倍数才能点准。
        # 普通屏 scale=1，此换算为恒等，无副作用。
        try:  # pragma: no cover - 取决于运行环境
            shot_w = pyautogui.screenshot().size[0]
            logical_w = pyautogui.size().width
            self.scale = shot_w / logical_w if logical_w else 1.0
        except Exception:  # pragma: no cover
            self.scale = 1.0
        logger.debug("屏幕缩放系数 scale=%.2f", self.scale)

    # ------------------------------------------------------------------ #
    # 应用与时间
    # ------------------------------------------------------------------ #
    def activate_app(self, bundle_id: str) -> None:
        """把目标应用置于前台。对应宏 ActivateApplication。

        **不会启动未运行的应用**：故意不用 AppleScript ``tell application … to
        activate``（它会把未运行的 App 拉起来），改用 System Events 设置进程
        ``frontmost``。进程不存在时静默跳过——是否运行由 :meth:`ensure_window`
        负责拦截。
        """
        logger.debug("激活应用 %s", bundle_id)
        if self.dry_run:
            return
        script = (
            'tell application "System Events"\n'
            f'  set procs to (every process whose bundle identifier is "{bundle_id}")\n'
            "  if procs is {} then return\n"
            "  set frontmost of item 1 of procs to true\n"
            "end tell"
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            raise GuiAutomationError(
                f"激活应用失败 {bundle_id}: {exc.stderr.decode(errors='ignore')}"
            ) from exc

    def app_window_status(self, bundle_id: str) -> str:
        """探测目标应用的窗口状态，返回以下之一：

        - ``"noproc"``  进程未运行（用户尚未启动微信）
        - ``"visible"`` 至少有一个未最小化的窗口，正常可见
        - ``"hidden"``  进程在运行，但窗口被最小化或前台关闭（无可见窗口）
        - ``"unknown"`` 查询失败（如权限不足 / 超时）

        用 System Events 按 bundle identifier 定位进程，不依赖（可能被本地化的）
        进程名。
        """
        script = (
            'tell application "System Events"\n'
            f'  set procs to (every process whose bundle identifier is "{bundle_id}")\n'
            '  if procs is {} then return "noproc"\n'
            "  set wins to windows of item 1 of procs\n"
            '  if (count of wins) is 0 then return "hidden"\n'
            "  repeat with w in wins\n"
            "    try\n"
            '      if (value of attribute "AXMinimized" of w) is false then return "visible"\n'
            "    on error\n"
            '      return "visible"\n'  # 取不到最小化属性的多为正常窗口，按可见处理
            "    end try\n"
            "  end repeat\n"
            '  return "hidden"\n'  # 有窗口但全部最小化
            "end tell"
        )
        try:
            out = subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):  # pragma: no cover
            return "unknown"
        status = out.stdout.decode(errors="ignore").strip()
        return status if status in ("noproc", "visible", "hidden") else "unknown"

    def ensure_window(self, bundle_id: str) -> None:
        """恢复被最小化 / 前台关闭的微信窗口。

        仅处理「微信已在运行、但当前没有可见窗口」的情况，用 ``open -b``
        （等效点击 Dock 图标，触发 reopen 事件）把主窗口重新弹出 / 取消最小化。

        **不会自动启动或重启微信**：若进程未运行，直接抛错，要求用户先手动
        启动微信——避免在用户没准备好时把程序拉起来。
        """
        if self.dry_run:
            return
        status = self.app_window_status(bundle_id)
        if status == "noproc":
            raise GuiAutomationError("微信未运行，请先手动启动并登录微信后再运行本工具。")
        if status == "unknown":
            logger.debug("无法确定 %s 的窗口状态，跳过弹窗", bundle_id)
            return
        if status == "visible":
            logger.debug("微信已有可见窗口")
            return
        # hidden：被最小化或前台关闭，触发 reopen 恢复（进程已在运行，不会重启）
        logger.info("微信窗口被最小化/关闭，正在恢复主窗口")
        subprocess.run(["open", "-b", bundle_id], check=False, timeout=10)

    @staticmethod
    def pause(seconds: float) -> None:
        """显式等待。对应宏 Pause 动作。"""
        if seconds > 0:
            time.sleep(seconds)

    # ------------------------------------------------------------------ #
    # 图像定位 / 点击
    # ------------------------------------------------------------------ #
    def locate(
        self,
        image: Path,
        *,
        confidence: Optional[float] = None,
    ) -> Optional[Point]:
        """在屏幕上定位模板图片，返回其中心坐标；找不到返回 ``None``。"""
        if not image.exists():
            raise GuiAutomationError(f"模板图片不存在：{image}")
        conf = self.confidence if confidence is None else confidence
        try:
            box = pyautogui.locateCenterOnScreen(
                str(image),
                confidence=conf,
                grayscale=self.grayscale,
            )
        except ImageNotFoundException:
            return None
        if box is None:
            return None
        # 物理坐标 -> 逻辑坐标（Retina 屏 scale=2，普通屏 scale=1）
        return int(box.x / self.scale), int(box.y / self.scale)

    def is_visible(self, image: Path, *, confidence: Optional[float] = None) -> bool:
        """判断某图片当前是否出现在屏幕上。对应宏 ScreenImage 条件。"""
        return self.locate(image, confidence=confidence) is not None

    def click_image(
        self,
        image: Path,
        *,
        confidence: Optional[float] = None,
        offset_x: int = 0,
        offset_y: int = 0,
        label: str = "",
    ) -> bool:
        """定位并点击图片（可带相对中心的像素偏移）。

        对应宏 MouseMoveAndClick(Relative=Image)。

        Returns:
            找到并点击返回 ``True``；未找到返回 ``False``（不抛异常，交由调用方决策）。
        """
        name = label or image.stem
        center = self.locate(image, confidence=confidence)
        if center is None:
            logger.info("未找到目标「%s」", name)
            return False
        x, y = center[0] + offset_x, center[1] + offset_y
        logger.info("点击「%s」-> (%d, %d)", name, x, y)
        if not self.dry_run:
            pyautogui.click(x, y)
        return True

    # ------------------------------------------------------------------ #
    # 键盘 / 文本
    # ------------------------------------------------------------------ #
    def hotkey(self, *keys: str, hold: float = 0.06) -> None:
        """组合键。对应宏 SimulateKeystroke（带修饰键）。

        不直接用 ``pyautogui.hotkey``：在 ``pyautogui.PAUSE=0`` 下它按键之间没有
        任何间隔，macOS 会因合成事件过快而让修饰键（如 command）来不及生效，
        导致 Cmd+F、Cmd+V 这类组合键静默失效。这里改为显式 keyDown/keyUp，
        并在按下修饰键后留出 ``hold`` 间隔，确保组合键可靠触发。
        """
        logger.debug("热键 %s", "+".join(keys))
        if self.dry_run:
            return
        for key in keys:                 # 依次按下（修饰键在前）
            pyautogui.keyDown(key)
            time.sleep(hold)
        for key in reversed(keys):       # 逆序释放
            pyautogui.keyUp(key)
            time.sleep(hold)

    def press(self, key: str) -> None:
        """单个按键，如 ``esc``。对应宏 SimulateKeystroke。"""
        logger.debug("按键 %s", key)
        if not self.dry_run:
            pyautogui.press(key)

    def type_text(self, text: str, *, interval: float = 0.02) -> None:
        """逐字符输入文本。对应宏 InsertText(ByTyping)。"""
        logger.debug("输入文本 %r", text)
        if not self.dry_run:
            # 中文无法靠 typewrite 逐键模拟，改用剪贴板粘贴
            self._paste_text(text)

    def _paste_text(self, text: str) -> None:
        """借助系统剪贴板 + Cmd+V 输入（兼容中文）。"""
        subprocess.run("pbcopy", input=text.encode("utf-8"), check=True)
        self.hotkey("command", "v")
