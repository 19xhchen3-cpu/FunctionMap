"""调用边数据模型"""

from dataclasses import dataclass, field


@dataclass
class CallEdge:
    """表示一次函数调用关系边"""
    caller_id: str              # 调用者函数ID
    callee_id: str              # 被调用函数ID（外部函数时可能未解析）
    call_line: int              # 调用发生的行号
    args: list[str] = field(default_factory=list)       # 调用时传入的实参
    is_resolved: bool = True    # 被调用函数是否在扫描范围内找到
    callee_name: str = ""       # 被调用函数名（即使未解析也能显示）

    @property
    def description(self) -> str:
        """描述这条调用关系"""
        return f"{self.caller_id} → {self.callee_id} (行 {self.call_line})"
