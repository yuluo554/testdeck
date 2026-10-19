"""框架识别：从 XML 的少量线索判定 pytest / gotestsum / playwright / unknown。

线索优先级（高 → 低，`detect` 按序短路）：

1. **根节点 / `<testsuite>` 的 `name` 属性**里出现框架名——pytest 会把
   `<testsuite name="pytest">`（根是 `<testsuites name="pytest tests">`）；
2. **`<testsuite>` 一级 `<properties>` 的键名**——gotestsum 写 `go.version`；
3. **文件名**——`gotestsum.xml` / `playwright.xml` / `junit*.xml`。

判不出写 ``unknown``——本项目宁可第三态也不猜（`plan/02` §五：「框架识别失败记
`unknown`，'猜'会污染统计」）。

**实测边界（务必知道）**：Playwright 的 `<testsuite name=...>` 是**测试文件名**
（如 `todo.spec.js`），`<testsuites name="">` 也是空串——它的产物里没有任何
"playwright" 字样，所以它只能靠**文件名**认出；gotestsum 的 suite name 是包名
（如 `demo-lib`）同样不带框架名，靠 `go.version` 或文件名。不要把"suite name"
当成通用线索。
"""

from __future__ import annotations

FRAMEWORK_UNKNOWN = "unknown"

#: 本项目首期认得出的框架（顺序即展示顺序）
FRAMEWORKS = ("pytest", "gotestsum", "playwright")

#: name 属性里的框架名线索
NAME_HINTS = (
    ("pytest", "pytest"),
    ("gotestsum", "gotestsum"),
    ("playwright", "playwright"),
)

#: testsuite 一级 properties 的键名线索（gotestsum 写 go.version）
PROPERTY_HINTS = (
    ("go.version", "gotestsum"),
)

#: 文件名线索；`junit` 是 pytest 的默认产物名（pytest 自己也会在 name 里写 pytest）
FILENAME_HINTS = (
    ("gotestsum", "gotestsum"),
    ("playwright", "playwright"),
    ("junit", "pytest"),
)


def _match(text, hints):
    """在 ``text`` 里找线索（小写子串匹配），命中返回框架名，否则 ``None``。"""
    lowered = (text or "").lower()
    if not lowered:
        return None
    for needle, name in hints:
        if needle in lowered:
            return name
    return None


def detect(file_name="", names=(), properties=()):
    """判定框架；判不出返回 ``FRAMEWORK_UNKNOWN``。

    - ``file_name``：产物文件名（含扩展名即可，路径会被取 basename）；
    - ``names``：根节点与各 `<testsuite>` 的 ``name`` 属性；
    - ``properties``：`<testsuite>` 一级 `<properties>` 的 ``name`` 键。
    """
    for value in names:
        hit = _match(value, NAME_HINTS)
        if hit:
            return hit
    for value in properties:
        hit = _match(value, PROPERTY_HINTS)
        if hit:
            return hit
    base = str(file_name).replace("\\", "/").rsplit("/", 1)[-1]
    return _match(base, FILENAME_HINTS) or FRAMEWORK_UNKNOWN
