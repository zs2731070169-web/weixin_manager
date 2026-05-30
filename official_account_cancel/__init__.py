"""微信公众号批量管理工具。

由 Keyboard Maestro「微信公众号管理」宏组翻译而来，核心能力是基于图像识别的
GUI 自动化，用于在 macOS 微信桌面客户端中批量取消关注公众号。

主要模块：
    - :mod:`official_account_cancel.config`   配置（路径、置信度、各步骤等待时间等）
    - :mod:`official_account_cancel.gui`      pyautogui 的薄封装（定位、点击、按键）
    - :mod:`official_account_cancel.workflow` 业务流程（单次取消 / 循环主流程）
    - :mod:`official_account_cancel.cli`      命令行入口
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
