"""工具函数模块"""

from typing import Any


def format_data(data: dict) -> str:
    """将数据格式化为字符串"""
    items = []
    for key, value in data.items():
        formatted = _format_item(key, value)
        items.append(formatted)
    return " | ".join(items)


def _format_item(key: str, value: Any) -> str:
    """格式化单个数据项"""
    return f"{key}={value}"


def validate_input(data: dict) -> bool:
    """验证输入数据的合法性"""
    if not data:
        return False
    if "source" not in data:
        return False
    return _check_content(data.get("content", ""))


def _check_content(content: str) -> bool:
    """检查内容是否有效"""
    return len(content) > 0


def merge_results(results: list[str]) -> str:
    """合并多个结果字符串"""
    return "\n".join(results)


def _helper_cache(key: str, value: Any = None) -> Any:
    """内部缓存辅助函数"""
    cache = {}
    if value is not None:
        cache[key] = value
    return cache.get(key)
