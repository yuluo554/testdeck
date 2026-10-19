"""键位单点守门（`plan/03` 模块②）：键位字面量只允许出现在 `keys.py`。

"任何地方另写键位字面量 = 缺陷"这条得能跑红，否则 `keys.py` 迟早退化成"其中一份"。
判据是 AST 扫 `src/` 里的**单字符字符串常量**，加上一份**穷尽式豁免表**：

- 豁免项必须写明理由（为什么它不是一个"键位"）；
- 豁免项**必须在仓库里真的出现**——登记了却不再出现也判红，
  免得豁免表变成"以后什么都往里塞"的垃圾桶。

`tests/test_keys_single_source.py` 是文件名，模块名 `test_keys_single_source`
与 `plan/03` 的引用一致。
"""

import ast
from pathlib import Path

from testdeck import keys

SRC = Path(__file__).resolve().parents[1] / "src" / "testdeck"

#: 键位字母表 = `keys.BINDINGS` 里**单字符**的那些键。
#: 判据是"出现了一个**恰好在字母表里**的单字符字符串常量"——而不是"任何单字符常量"。
#: 后者会把 `"+"` / `"\n"` / `"—"` / `"█"` 这类与键位无关的东西全扫进来，
#: 逼着人往豁免表里塞几十条噪声（豁免表一烂，守门就废了）。
KEY_ALPHABET = frozenset(
    key for key in keys.BINDINGS.values() if len(key) == 1
)

#: 合法出现"键位同形字符"的地方（穷尽式：登记了却不出现 → 判红）
#:
#: 只登记**确实与键位同形**（`/` 与 `?`）的那些；反斜杠之类不在键位字母表里，
#: 压根不会被扫到，登记它只会让豁免表多一条永远不会命中的噪声。
ALLOWED_SINGLE_CHAR_LITERALS = {
    ("framework.py", "/"): "路径分隔符（正斜杠归一），不是键位",
    ("paths.py", "/"): "路径分隔符（正斜杠归一），不是键位",
    ("model.py", "?"): "缺失状态的字形（STATUS_GLYPHS），不是键位",
    ("queries.py", "?"): "SQL 占位符，不是键位",
    ("view.py", "?"): "状态字形兜底（未知状态的显示），不是键位",
    ("view.py", "/"): "比例式里的斜杠（文案），不是键位",
    ("slow.py", "?"): "回归不可判的三态渲染（reg=yes/no/?），不是键位",
}

#: 键位表自身的豁免（唯一允许写键位字面量的文件）
KEYS_FILE = "keys.py"


def _single_char_strings(tree):
    """返回 ``[(行号, 值)]``：所有**落在键位字母表里**的单字符字符串常量。"""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) == 1 and node.value in KEY_ALPHABET:
            found.append((node.lineno, node.value))
    return found


def _scan():
    """扫 `src/testdeck/**/*.py`，返回 ``(违规清单, 命中豁免清单)``。"""
    violations = []
    used_exemptions = set()
    for path in sorted(SRC.rglob("*.py")):
        if path.name == KEYS_FILE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, value in _single_char_strings(tree):
            key = (path.name, value)
            if key in ALLOWED_SINGLE_CHAR_LITERALS:
                used_exemptions.add(key)
                continue
            violations.append("%s:%d 单字符字面量 %r" % (path.name, lineno, value))
    return violations, used_exemptions


def test_keys_file_exists_and_is_the_source():
    """`keys.py` 在位，且导出 `BINDINGS` / `KEYS` / `description_for`。"""
    from testdeck import keys
    assert keys.BINDINGS and keys.KEYS
    assert callable(keys.description_for)
    assert set(keys.BINDINGS) == {
        "down", "up", "first", "last", "enter", "flaky", "slow", "diff",
        "search", "export", "help", "back", "quit",
    }


def test_no_key_literal_outside_keys_py():
    """除 `keys.py` 与豁免表外，`src/` 里不得出现单字符键位字面量。"""
    violations, _ = _scan()
    assert violations == [], (
        "键位字面量出现在 keys.py 之外：%s\n"
        "（键位只能来自 keys.BINDINGS；若这是别的东西，请登记到 "
        "ALLOWED_SINGLE_CHAR_LITERALS 并写明理由）" % violations)


def test_exemptions_are_exhaustive_not_a_dumping_ground():
    """豁免表必须被**用满**：登记了却不出现 → 判红（防豁免表腐化）。"""
    _violations, used = _scan()
    unused = sorted(set(ALLOWED_SINGLE_CHAR_LITERALS) - used)
    assert unused == [], "豁免登记了却不存在（过期/写错）：%s" % unused


def test_app_bindings_come_from_keys():
    """`app.py` 的 `BINDINGS` 由 `keys.BINDINGS` 生成，不另写字面量。"""
    text = (SRC / "tui" / "app.py").read_text(encoding="utf-8")
    assert "keys.BINDINGS.items()" in text
    assert "keys.description_for(" in text
    # 反向：不该出现"手写键位表"的形态
    for banned in ('Binding("j"', "Binding('j'", 'Binding("F"', "Binding('F'"):
        assert banned not in text, "app.py 里手写了键位：%s" % banned


def test_footer_and_help_use_the_display_table():
    """Footer 由 `keys.KEYS`（经 app 的 BINDINGS）驱动，帮助层由 `view.help_text` 生成。"""
    app_text = (SRC / "tui" / "app.py").read_text(encoding="utf-8")
    assert "yield Footer()" in app_text
    assert "Binding(key, action, keys.description_for(action)" in app_text
    view_text = (SRC / "tui" / "view.py").read_text(encoding="utf-8")
    assert "for label, text in keys.KEYS" in view_text


def test_help_screen_bindings_also_come_from_keys():
    """帮助层自己的关闭键同样取自 `keys.BINDINGS`（否则又多一份键位）。"""
    text = (SRC / "tui" / "app.py").read_text(encoding="utf-8")
    assert "keys.BINDINGS[\"back\"]" in text
    assert "keys.BINDINGS[\"help\"]" in text


def test_scan_face_is_not_empty():
    """非空跑自证：真的扫到了源码文件（否则"没有违规"毫无意义）。"""
    files = sorted(SRC.rglob("*.py"))
    assert len(files) >= 15, len(files)
