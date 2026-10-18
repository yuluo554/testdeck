"""键位表（唯一来源）：Footer、帮助层与 Pilot 测试三处共用。

改动这里等于改动三处；任何地方另写键位字面量都是缺陷。
`BINDINGS` 是动作 → 键的映射，`KEYS` 是给人看的展示顺序（覆盖全部动作）。
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
}

KEYS = (
    ("j", "下一项（down）"),
    ("k", "上一项（up）"),
    ("g", "跳到首（first）"),
    ("G", "跳到尾（last）"),
    ("Enter", "展开或进入（enter）"),
    ("F", "flaky 矩阵"),
    ("S", "慢测试瀑布"),
    ("D", "两次 run diff"),
    ("/", "搜索"),
    ("e", "导出当前视图"),
    ("?", "帮助"),
)
