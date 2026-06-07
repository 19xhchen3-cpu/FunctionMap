"""Qt UI (.ui) 文件解析器 - 解析 Qt Designer XML 界面文件"""

import os
import xml.etree.ElementTree as ET

from models.function_node import FunctionNode
from models.call_edge import CallEdge
from parsers.base_parser import BaseParser


class UiParser(BaseParser):
    """
    Qt Designer .ui 文件解析器

    从 XML 格式的 .ui 文件中提取：
    - 表单类名（如 MainWindow）
    - 所有 widget 名称（如 centralWidget, pushButton）
    - 自定义 widget 注册信息

    解析器不会产生调用边（CallEdge），边由后续的跨语言链接步骤生成。
    """

    def get_language(self) -> str:
        return 'ui'

    def parse_file(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """解析 .ui 文件，提取表单类和 widget 信息"""
        functions: list[FunctionNode] = []
        edges: list[CallEdge] = []

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"  警告: 无法解析UI文件 {file_path}: {e}")
            return functions, edges
        except Exception as e:
            print(f"  警告: 无法读取UI文件 {file_path}: {e}")
            return functions, edges

        # 提取表单类名
        class_elem = root.find('class')
        form_class = class_elem.text if class_elem is not None else 'Form'

        # 添加表单本身作为一个伪函数节点
        form_id = f"{file_path}::{form_class}"
        functions.append(FunctionNode(
            id=form_id,
            name=form_class,
            file_path=file_path,
            line_start=1,
            line_end=1,
            language='ui',
            params=[],
            return_type='QWidget',
            class_name='',
        ))

        # 遍历所有 widget，提取名称作为伪函数节点
        seen_widgets: set[str] = set()
        for widget_elem in root.iter('widget'):
            widget_name = widget_elem.get('name')
            if not widget_name or widget_name in seen_widgets:
                continue
            seen_widgets.add(widget_name)

            display_name = f"{form_class}.{widget_name}"
            func_id = f"{file_path}::{display_name}"

            # 粗略估算节点行数（用于排序，非精确行号）
            widget_xml = ET.tostring(widget_elem, encoding='unicode')
            n_lines = max(1, widget_xml.count('\n') + 1)

            functions.append(FunctionNode(
                id=func_id,
                name=widget_name,
                file_path=file_path,
                line_start=1,
                line_end=n_lines,
                language='ui',
                params=[],
                return_type='',
                class_name=form_class,
            ))

        return functions, edges
