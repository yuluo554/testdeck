"""退出码语义（唯一来源）。

0 = 达标 / 1 = 门禁触发 / 2 = 用法错误或未知命令 / 3 = 依赖缺失或库不可读。
4 = 骨架期"尚未实现"——只在 M0 存在，M2 起逐命令退役（见 plan/05）。
"""

OK = 0
GATE_TRIGGERED = 1
USAGE = 2
DEPENDENCY = 3
NOT_READY = 4
