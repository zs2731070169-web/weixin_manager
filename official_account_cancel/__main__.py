"""支持 ``python -m official_account_cancel`` 方式运行。"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
