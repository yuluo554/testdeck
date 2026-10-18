"""路径口径：数据库位置、路径归一、相对扫描根。

规则（见 data/README.md §四）：
  - 库位置 = ``$XDG_DATA_HOME/testdeck/testdeck.db``，未设置时 ``~/.local/share/testdeck/testdeck.db``；
  - 路径统一正斜杠；入库存相对扫描根的形式（跨机器可复现，不泄露本机目录）；
  - ``--db`` 覆盖值必须回显，调用方负责打印（本模块只解析）。
"""

from __future__ import annotations

import os

APP_DIRNAME = "testdeck"
DB_FILENAME = "testdeck.db"


def data_home(env=None):
    """返回本应用的数据根目录（不创建）。"""
    env = os.environ if env is None else env
    xdg = env.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return os.path.join(xdg, APP_DIRNAME)
    return os.path.join(os.path.expanduser("~"), ".local", "share", APP_DIRNAME)


def default_db_path(env=None):
    return os.path.join(data_home(env), DB_FILENAME)


def resolve_db_path(explicit, env=None):
    """把 ``--db`` 的取值解析成最终路径。

    - ``None`` -> 默认库路径；
    - ``""`` / 纯空白 -> 用法错误（不静默回落到默认库——这是 ``or DEFAULT`` 的经典坑）；
    - 其他 -> ``expanduser`` 后的原样路径。
    """
    if explicit is None:
        return default_db_path(env)
    if not str(explicit).strip():
        raise ValueError("--db must not be empty (omit it to use the default database)")
    return os.path.expanduser(str(explicit))


def normalize_path(path):
    """统一正斜杠，去掉 ``./`` 前缀；不做 realpath（保留用户给的形态）。"""
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def relative_to_root(path, root):
    """相对扫描根的正斜杠路径；跨盘符等无法相对化时回落绝对路径。

    ``os.path.relpath`` 在 Windows 跨盘符会抛 ``ValueError``——这是实测坑，
    不能让它逃逸成崩溃。
    """
    try:
        rel = os.path.relpath(str(path), str(root))
    except ValueError:
        rel = str(path)
    return normalize_path(rel)
