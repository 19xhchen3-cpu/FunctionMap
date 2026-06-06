"""函数节点数据模型"""

from dataclasses import dataclass, field


@dataclass
class FunctionNode:
    """表示一个被解析出的函数定义"""
    id: str                     # 唯一标识: "文件路径::函数名"
    name: str                   # 函数名
    file_path: str              # 所在源文件路径
    line_start: int             # 定义起始行号
    line_end: int               # 定义结束行号
    language: str               # 语言: "python" | "cpp" | "c" | "matlab"
    params: list[str] = field(default_factory=list)    # 参数名列表
    return_type: str = ""       # 返回值类型（未知时为空）
    class_name: str = ""        # 所属类名（自由函数时为空）

    @property
    def short_name(self) -> str:
        """返回可读性更好的短名称（含类名前缀）"""
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name

    @property
    def signature(self) -> str:
        """返回函数签名：函数名(参数1, 参数2, ...)"""
        return f"{self.short_name}({', '.join(self.params)})"
