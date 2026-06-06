"""主模块 - 处理数据流"""

from test_project.utils import format_data, validate_input
from test_project.processor import process_data


def load_data(source: str) -> dict:
    """从数据源加载数据"""
    print(f"Loading data from {source}")
    raw = {"source": source, "content": "sample data"}
    return raw


def analyze_and_report(data_source: str) -> str:
    """分析数据并生成报告"""
    raw_data = load_data(data_source)
    valid = validate_input(raw_data)
    if valid:
        result = process_data(raw_data)
        report = format_data(result)
        return report
    return "Invalid data"


def run_pipeline(sources: list[str]) -> list[str]:
    """批量运行数据处理流水线"""
    reports = []
    for src in sources:
        report = analyze_and_report(src)
        reports.append(report)
    return reports


if __name__ == "__main__":
    result = run_pipeline(["file1.txt", "file2.csv"])
    print(result)
