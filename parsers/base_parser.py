"""解析器抽象基类"""

from abc import ABC, abstractmethod

from models.function_node import FunctionNode
from models.call_edge import CallEdge


class BaseParser(ABC):
    """所有语言解析器的抽象基类"""

    @abstractmethod
    def parse_file(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """
        解析单个文件，提取函数定义和调用关系

        参数:
            file_path: 源文件的绝对路径

        返回:
            (函数节点列表, 调用边列表) 的元组
        """
        ...

    def get_language(self) -> str:
        """返回该解析器支持的语言名称"""
        raise NotImplementedError
