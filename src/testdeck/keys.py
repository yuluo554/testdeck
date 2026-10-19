"""键位表（唯一来源）：Footer、帮助层与 Pilot 测试三处共用。

改动这里等于改动三处；任何地方另写键位字面量都是缺陷
（`tests/test_keys_single_source.py` 用 AST 扫描钉住这条）。

- ``BINDINGS``：动作 → 键（Textual 的键名形态，如 ``"escape"`` / ``"enter"``）；
- ``KEYS``：给人看的展示顺序，覆盖全部动作（Footer 与帮助层从它生成）；
- ``description_for(action)``：动作 → 展示文案（app.py 生成 ``Binding`` 时用）。

键位字面量在别处**只有两种合法用途**：路径分隔符（`framework.py` / `paths.py`
的 `"/"`）与状态字形（`model.py` 的 `"?"`）。两者都在
`tests/test_keys_single_source.py` 的豁免表里带理由登记，且豁免是**穷尽式**的：
登记了却不再出现 → 判红（防"豁免变成垃圾桶"）。
"""

BINDINGS = {
    "down": "j",
    "up": "k",
    "first": "g",
    "last": "G",
    "enter": "enter",
    "flaky": "F",
    "slow": "S",
    "diff": "D",
    "search": "/",
    "export": "e",
    "help": "?",
    "back": "escape",
    "quit": "q",
}

KEYS = (
    ("j", "下一项（down）"),
    ("k", "上一项（up）"),
    ("g", "跳到首（first）"),
    ("G", "跳到尾（last）"),
    ("Enter", "展开 / 进入详情（enter）"),
    ("F", "flaky 矩阵"),
    ("S", "慢测试瀑布"),
    ("D", "两次 run diff"),
    ("/", "搜索"),
    ("e", "导出当前视图"),
    ("?", "帮助"),
    ("Esc", "返回三栏（back）"),
    ("q", "退出（quit）"),
)

#: 展示表键面 → 绑定值键面的归一（Textual 用 ``enter`` / ``escape``，给人看用 Enter / Esc）
DISPLAY_LABELS = {"enter": "Enter", "escape": "Esc"}

_DESCRIPTIONS_BY_LABEL = {label: text for label, text in KEYS}


def display_label(key):
    """绑定值 → 展示表键面。"""
    return DISPLAY_LABELS.get(key, key)


def description_for(action):
    """动作 → 展示文案（缺条目返回空串，不编造）。"""
    key = BINDINGS.get(action, "")
    return _DESCRIPTIONS_BY_LABEL.get(display_label(key), "")
