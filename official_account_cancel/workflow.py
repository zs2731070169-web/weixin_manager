"""批量取消关注公众号的业务流程。

逐一翻译 Keyboard Maestro「微信公众号管理」宏组中的四个宏：

================  ==========================================================
原宏              对应实现
================  ==========================================================
取消微信公众号      :meth:`UnsubscribeWorkflow.run`        循环主流程
取消公众号_单次     :meth:`UnsubscribeWorkflow.run_single` 单次取消
取消微信公众号正常分支  :meth:`UnsubscribeWorkflow._normal_branch`
取消微信公众号失败分支  :meth:`UnsubscribeWorkflow._fail_branch`
================  ==========================================================

单次流程：
    激活微信 → Cmd+F 打开搜索 → 输入「公众号」→ 点击搜索结果 →
    点击第一个公众号 → 点击「已关注」→ 弹出菜单后判定分支：
        · 若出现「取消关注」按钮 → 正常分支（取消关注 → 连续确认 → Esc）
        · 否则                  → 失败分支（连续确认 → Esc）

主流程：不断执行单次取消，直到某一步关键图片找不到（视为列表已清空 /
没有更多公众号）或达到安全上限为止。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings
from .gui import GuiController

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    """一次完整运行的统计结果。"""

    processed: int = 0          # 成功取消的数量
    normal_branch: int = 0      # 走正常分支次数
    fail_branch: int = 0        # 走失败分支次数
    stopped_reason: str = ""    # 终止原因


class UnsubscribeWorkflow:
    """批量取消关注公众号的工作流。"""

    def __init__(self, settings: Settings, gui: GuiController) -> None:
        self.s = settings
        self.gui = gui
        self.stats = RunStats()

    # ------------------------------------------------------------------ #
    # 主流程（对应「取消微信公众号」）
    # ------------------------------------------------------------------ #
    def run(self) -> RunStats:
        """循环执行单次取消，直到无更多公众号或触达安全上限。"""
        logger.info("开始批量取消订阅流程（按 Ctrl+C 可随时停止）")
        try:
            for i in range(1, self.s.max_iterations + 1):
                logger.info("—— 第 %d 轮 ——", i)
                if not self.run_single():
                    self.stats.stopped_reason = "没有更多可取消的公众号"
                    break
                self.stats.processed += 1
            else:
                self.stats.stopped_reason = f"已达安全上限 {self.s.max_iterations} 轮"
        except KeyboardInterrupt:
            self.stats.stopped_reason = "用户中断（Ctrl+C）"
            logger.warning("收到中断信号，已停止")

        logger.info(
            "流程结束：成功取消 %d 个（正常分支 %d / 失败分支 %d），原因：%s",
            self.stats.processed,
            self.stats.normal_branch,
            self.stats.fail_branch,
            self.stats.stopped_reason,
        )
        return self.stats

    # ------------------------------------------------------------------ #
    # 单次流程（对应「取消公众号_单次」）
    # ------------------------------------------------------------------ #
    def run_single(self) -> bool:
        """执行一次「搜索→进入第一个公众号→取消关注」。

        Returns:
            ``True``  表示本轮成功取消，可继续下一轮；
            ``False`` 表示关键步骤的目标缺失（通常意味着列表已空），应停止循环。
        """
        s, gui, t = self.s, self.gui, self.s.timings

        # 1. 先确认微信已启动,如果启动了会自动弹窗
        gui.ensure_window(s.wechat_bundle_id)
        gui.pause(t.after_activate)

        # 再激活微信置于前台
        gui.activate_app(s.wechat_bundle_id)
        gui.pause(t.after_activate)

        # 2. Cmd+F 打开搜索
        gui.hotkey("command", "f")
        gui.pause(t.after_open_search)

        # 3. 输入搜索关键字
        gui.type_text(s.search_keyword)
        gui.pause(t.after_type_keyword)

        # 4. 点击搜索结果中的「公众号」入口
        if not gui.click_image(
            s.asset(s.img_search_result),
            confidence=s.search_result_confidence,
            label="公众号(搜索结果)",
        ):
            return False
        gui.pause(t.after_click_result)

        # 5. 点击第一个公众号
        if not gui.click_image(
            s.asset(s.img_first_account),
            offset_y=s.first_account_click_offset_y,
            label="第一个公众号",
        ):
            return False
        gui.pause(t.after_click_account)

        # 6. 点击「已关注」展开菜单
        if not gui.click_image(s.asset(s.img_following_button), label="已关注"):
            return False
        gui.pause(t.after_click_following)

        # 7. 分支判定：菜单里是否出现「取消关注」按钮
        if gui.is_visible(s.asset(s.img_branch_marker)):
            self._normal_branch()
            self.stats.normal_branch += 1
        else:
            self._fail_branch()
            self.stats.fail_branch += 1
        gui.pause(t.after_branch_decision)
        return True

    # ------------------------------------------------------------------ #
    # 正常分支（对应「取消微信公众号正常分支」）
    # ------------------------------------------------------------------ #
    def _normal_branch(self) -> None:
        """菜单中存在「取消关注」时：点取消关注 → 连续 3 次确认 → Esc。"""
        s, gui, t = self.s, self.gui, self.s.timings
        logger.info("进入正常分支")

        gui.click_image(s.asset(s.img_normal_unfollow), label="取消关注")
        gui.pause(t.normal_between_clicks)

        for img in (s.img_normal_confirm_1, s.img_normal_confirm_2, s.img_normal_confirm_3):
            gui.click_image(s.asset(img), label="确认")
            gui.pause(t.normal_between_clicks)

        # 兜底退出弹窗，避免卡住影响下一轮
        gui.press("esc")
        gui.pause(t.normal_after_escape)

    # ------------------------------------------------------------------ #
    # 失败分支（对应「取消微信公众号失败分支」）
    # ------------------------------------------------------------------ #
    def _fail_branch(self) -> None:
        """菜单未出现「取消关注」时：直接连续确认 → Esc。

        原宏在第一次确认后等待较久（2.5s），用于处理需要二次确认 / 反应较慢的弹窗。
        """
        s, gui, t = self.s, self.gui, self.s.timings
        logger.info("进入失败分支")

        gui.click_image(s.asset(s.img_fail_confirm_1), label="确认")
        gui.pause(t.fail_after_first_confirm)

        gui.click_image(s.asset(s.img_fail_confirm_2), label="确认")
        gui.pause(t.fail_between_clicks)

        gui.click_image(s.asset(s.img_fail_confirm_3), label="确认")
        gui.pause(t.fail_between_clicks)

        gui.press("esc")
        gui.pause(t.fail_after_escape)
