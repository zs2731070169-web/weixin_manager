# weixin_manager — 微信自动化管理

面向 macOS 微信桌面客户端的**自动化管理工具集**，基于**图像识别的 GUI 自动化**
（模板图片匹配 → 定位 → 点击/输入）驱动微信完成重复性操作。

## 功能

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 批量取消关注公众号<br>[`official_account_cancel`](official_account_cancel) | ✅ 已支持 | 自动搜索、进入并逐个取消关注公众号 |
| 更多自动化管理操作 | 🚧 规划中 | 后续按需扩展（如批量清理、消息管理等） |

> 当前的取消公众号模块由 Keyboard Maestro「微信公众号管理」宏组逐动作翻译为符合
> 工程标准的 Python 实现。原宏通过模板图片匹配定位并点击界面元素，本项目沿用同一
> 思路，但把硬编码的等待时长、容差、坐标偏移等外置到
> [`config.yml`](official_account_cancel/config.yml)，并补充了日��、命令行参数、dry-run、
> 安全急停、Retina 坐标自适配、窗口自动恢复等工程能力。

## 目录结构

```
weixin_manager/
├── assets/                     # 模板图片（PNG），各模块共用
├── official_account_cancel/    # 取消公众号模块
│   ├── config.yml              # 配置文件（路径/置信度/等待时长/安全限制）← 调参改这里
│   ├── config.py               # 读取 config.yml，解析为强类型配置
│   ├── gui.py                  # pyautogui 薄封装（激活/窗口恢复/定位/点击/按键）
│   ├── workflow.py             # 业务流程（单次/正常分支/失败分支/主循环）
│   ├── cli.py                  # 命令行入口
│   └── __main__.py             # python -m official_account_cancel
├── requirements.txt
├── pyproject.toml
└── README.md
```

> 后续新增的自动化模块会作为与 `official_account_cancel/` 平级的独立包加入。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### macOS 系统权限（必须）

终端 / Python 解释器需要被授予以下权限，否则无法控制鼠标键盘或截屏识别：

- **系统设置 → 隐私与安全性 → 辅助功能**：勾选你的终端（如 Terminal / iTerm）
- **系统设置 → 隐私与安全性 → 屏幕录制**：同上

---

## 取消公众号

> ⚠️ **前置条件：请先手动启动并登录微信。** 本工具**不会自动启动 / 重启微信**；
> 若运行时检测到微信进程未运行，会直接报错退出。仅当微信已在运行、但窗口被
> 最小化或前台关闭时，才会自动恢复其主窗口。

### 工作原理

单次取消流程（对应原宏「取消公众号_单次」）：

```
激活微信（窗口被最小化/关闭则自动恢复）→ Cmd+F 搜索「公众号」→ 点击搜索结果
→ 点击第一个公众号 → 点击「已关注」展开菜单 → 判定分支：
     ├─ 菜单出现「取消关注」  → 正常分支：取消关注 → 连续确认 → Esc
     └─ 未出现               → 失败分支：连续确认 → Esc
```

主流程（对应「取消微信公众号」）不断重复单次流程，直到：
- 某一关键图片找不到（视为列表已无更多公众号），或
- 达到 `--max` / 配置中的安全上限，或
- 微信进程不再运行（视为用户已退出微信），或
- 用户 `Ctrl+C` 中断。

### 使用

```bash
# 联调：只���别、打印日志，不真正点击
python -m official_account_cancel --dry-run -v

# 正式运行（开始前有倒计时，可 Ctrl+C 取消）
python -m official_account_cancel

# 最多取消 20 个，并调高匹配严格度
python -m official_account_cancel --max 20 --confidence 0.9
```

#### 常用参数

| 参数 | 说明 |
| --- | --- |
| `--config PATH` | 自定义 YAML 配置文件路径（默认用包内 `config.yml`） |
| `--dry-run` | 只识别不操作 |
| `--max N` | 最多处理 N 个公众号 |
| `--confidence 0~1` | 图像匹配置信度，越大越严格 |
| `--countdown SEC` | 开始前倒计时秒数 |
| `--no-failsafe` | 关闭「鼠标甩到屏幕角落急停」（不建议） |
| `-v / --verbose` | DEBUG 级日志 |

### 配置

所有可调参数集中在 [`official_account_cancel/config.yml`](official_account_cancel/config.yml)，
分三块：顶层（目标应用 / 搜索关键字 / 匹配置信度 / 点击偏移 / 安全节流）、
`timings`（各步骤等待时长）、`images`（模板图片文件名）。直接编辑该文件即可调参，
无需改动代码。

也可用 `--config 另一份.yml` 切换到自定义配置。优先级为
**命令行参数 > 配置文件 > 代码内置默认**（配置文件缺失时自动回退内置默认，保证可运行）。

### 调参建议

不同分辨率 / 缩放 / 微信版本可能导致模板匹配失败，可优先调整 `config.yml`：

- **置信度**：识别不到就调低 `search_result_confidence` / `confidence`（如 0.75）；误点就调高。
- **等待时长**：网络/动画慢导致点空，适当增大 `timings` 段里的值。
- **模板图片**：若微信改版导致按钮样式变化，重新截图替换 `assets/` 下对应 PNG 即可。

> Retina（高分屏）下的物理/逻辑坐标换算已由 `gui.py` 自动处理，无需手动调整。

### 安全提示

- 该工具会**真实地取消关注**，操作不可逆，请先用 `--dry-run` 确认识别正确。
- 运行期间请勿移动鼠标 / 切换窗口；急停方式：把鼠标快速甩到屏幕**任一角落**。
- 仅在你自己的账号、自担风险使用。

---

## 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。详见 [LICENSE](LICENSE) 文件。

在使用本项目时，你可以自由使用、修改和分发该代码，但需要包含原始的许可证声明。
