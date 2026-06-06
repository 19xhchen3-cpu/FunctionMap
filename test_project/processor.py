"""数据处理模块"""

from typing import Any


class DataProcessor:
    """数据处理器的基类"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._initialized = True

    def process(self, data: dict) -> dict:
        """处理数据"""
        if not self._validate(data):
            return {"error": "validation failed"}
        transformed = self._transform(data)
        enriched = self._enrich(transformed)
        return enriched

    def _validate(self, data: dict) -> bool:
        """内部数据验证"""
        return "content" in data

    def _transform(self, data: dict) -> dict:
        """数据转换"""
        result = dict(data)
        result["processed"] = True
        return result

    def _enrich(self, data: dict) -> dict:
        """数据增强"""
        if self.config.get("verbose"):
            data["detail"] = self._get_detail(data)
        return data

    def _get_detail(self, data: dict) -> str:
        """获取详细信息"""
        return f"Detail: {data.get('content', '')}"


class FastProcessor(DataProcessor):
    """快速处理器的优化版本"""

    def __init__(self):
        super().__init__({"verbose": False})
        self._fast_mode = True

    def process(self, data: dict) -> dict:
        if self._fast_mode and not data.get("complex"):
            return self._fast_path(data)
        return super().process(data)

    def _fast_path(self, data: dict) -> dict:
        """快速处理路径"""
        return {"result": "fast", "source": data.get("source")}


def process_data(data: dict) -> dict:
    """便捷的数据处理函数（工厂方式）"""
    processor = FastProcessor()
    return processor.process(data)


def batch_process(data_list: list[dict]) -> list[dict]:
    """批量处理数据"""
    processor = DataProcessor()
    return [processor.process(d) for d in data_list]
