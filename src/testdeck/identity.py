"""身份键的单点定义（run 与用例）。

run 身份 = (branch, commit_sha, ci_run_id)
用例身份 = (suite_name, classname, name)   —— 参数化用例保留完整参数串，不做归一

两条身份都做成不可变的 dataclass，避免"两个模块各自拼字符串"导致的键漂移。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEX40 = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, order=True)
class RunIdentity:
    branch: str
    commit_sha: str
    ci_run_id: str

    def __post_init__(self):
        # 未知值写空串（不是 None）：NULL 在唯一索引里彼此不等，会绕过 upsert
        for field in ("branch", "commit_sha", "ci_run_id"):
            if getattr(self, field) is None:
                raise ValueError("%s must be a string (use '' for unknown)" % field)
        if self.commit_sha and not _HEX40.match(self.commit_sha):
            raise ValueError(
                "commit_sha must be 40 lowercase hex chars or '' (got %r)" % self.commit_sha
            )

    @property
    def key(self):
        return (self.branch, self.commit_sha, self.ci_run_id)


@dataclass(frozen=True, order=True)
class CaseIdentity:
    suite_name: str
    classname: str
    name: str

    def __post_init__(self):
        for field in ("suite_name", "classname", "name"):
            if getattr(self, field) is None:
                raise ValueError("%s must be a string (use '' for unknown)" % field)
        if not self.name:
            raise ValueError("case name must not be empty")

    @property
    def key(self):
        return (self.suite_name, self.classname, self.name)

    @property
    def display(self):
        parts = [p for p in (self.suite_name, self.classname, self.name) if p]
        return " :: ".join(parts)
