"""Python解析器 - 基于内置ast模块（零额外依赖）"""

import ast
import os

from models.function_node import FunctionNode
from models.call_edge import CallEdge
from parsers.base_parser import BaseParser


class PythonParser(BaseParser):
    """使用Python内置ast模块解析Python源文件"""

    def get_language(self) -> str:
        return 'python'

    def parse_file(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """
        解析Python文件，提取函数定义和调用关系

        特点:
        - 正确处理嵌套函数和类方法
        - 支持async def
        - 类方法包含类名前缀
        - lambda不单独作为函数节点（但调用时可能被识别）
        - 通过ast内置模块实现，零额外依赖
        """
        functions: list[FunctionNode] = []
        calls: list[CallEdge] = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
        except Exception as e:
            print(f"  警告: 无法读取文件 {file_path}: {e}")
            return functions, calls

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            print(f"  警告: 语法错误 {file_path}:{e.lineno} - {e.msg}")
            return functions, calls

        # 第一遍：收集所有函数定义
        func_info = {}  # node_id -> (FunctionNode, lineno)
        self._collect_functions(tree, file_path, functions, func_info)

        # 第二遍：收集所有函数调用
        self._collect_calls(tree, file_path, source, functions, calls, func_info)

        return functions, calls

    def _collect_functions(self, node: ast.AST, file_path: str,
                           functions: list[FunctionNode],
                           func_info: dict) -> None:
        """
        递归遍历AST，收集所有函数/方法定义
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 构建函数节点
                func_node = self._build_function_node(child, file_path)
                functions.append(func_node)
                func_info[func_node.id] = func_node

                # 继续遍历函数体内部（查找嵌套函数）
                self._collect_functions(child, file_path, functions, func_info)

            elif isinstance(child, ast.ClassDef):
                # 遍历类内部的方法
                self._collect_class_methods(child, file_path, functions, func_info)

    def _collect_class_methods(self, class_node: ast.ClassDef, file_path: str,
                               functions: list[FunctionNode],
                               func_info: dict) -> None:
        """收集类中的所有方法"""
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 构建方法节点（含类名前缀）
                func_node = self._build_function_node(item, file_path,
                                                       class_name=class_node.name)
                functions.append(func_node)
                func_info[func_node.id] = func_node

                # 嵌套在方法内部的函数
                self._collect_functions(item, file_path, functions, func_info)

    def _build_function_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef,
                              file_path: str,
                              class_name: str = '') -> FunctionNode:
        """从AST节点构建FunctionNode"""
        func_name = node.name

        # 提取参数名
        params: list[str] = []
        for arg in node.args.args:
            params.append(arg.arg)
        # 处理 *args
        if node.args.vararg:
            params.append(f"*{node.args.vararg.arg}")
        # 处理 **kwargs
        if node.args.kwarg:
            params.append(f"**{node.args.kwarg.arg}")

        # 构建唯一ID
        display_name = f"{class_name}.{func_name}" if class_name else func_name
        func_id = f"{file_path}::{display_name}"

        return FunctionNode(
            id=func_id,
            name=func_name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=getattr(node, 'end_lineno', node.lineno),
            language='python',
            params=params,
            return_type=self._get_return_annotation(node),
            class_name=class_name,
        )

    def _get_return_annotation(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """提取返回值类型注解"""
        if node.returns is None:
            return ''

        if isinstance(node.returns, ast.Name):
            return node.returns.id
        elif isinstance(node.returns, ast.Subscript):
            # 例如 List[str]
            return ast.unparse(node.returns) if hasattr(ast, 'unparse') else ''
        elif isinstance(node.returns, ast.Constant):
            return str(node.returns.value)

        return ast.unparse(node.returns) if hasattr(ast, 'unparse') else ''

    def _collect_calls(self, node: ast.AST, file_path: str,
                       source: str,
                       functions: list[FunctionNode],
                       calls: list[CallEdge],
                       func_info: dict) -> None:
        """
        递归遍历AST，收集所有函数调用关系
        """
        for child in ast.walk(node):
            # 跳过函数定义内部（避免把函数名本身当调用）
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            if isinstance(child, ast.Call):
                self._process_call(child, file_path, source,
                                   functions, calls, func_info)

    def _process_call(self, call_node: ast.Call, file_path: str,
                      source: str,
                      functions: list[FunctionNode],
                      calls: list[CallEdge],
                      func_info: dict) -> None:
        """处理一个函数调用节点"""
        # 获取被调用函数名
        callee_name = self._get_call_name(call_node.func)
        if not callee_name:
            return

        # 查找这个调用在哪个函数体内
        caller_node = self._find_enclosing_function(call_node, file_path, functions)
        if not caller_node:
            return

        # 提取调用的实参
        args = []
        for arg in call_node.args:
            if isinstance(arg, ast.Constant):
                args.append(repr(arg.value))
            elif isinstance(arg, ast.Name):
                args.append(arg.id)
            elif isinstance(arg, ast.Starred):
                args.append(f"*{arg.value.id if isinstance(arg.value, ast.Name) else '...'}")
            else:
                try:
                    args.append(ast.unparse(arg)[:50])  # 截断长表达式
                except Exception:
                    args.append('...')

        # 关键字参数
        kwargs = []
        for kw in call_node.keywords:
            if kw.arg is None:
                kwargs.append(f"**{kw.value.id if isinstance(kw.value, ast.Name) else '...'}")
            elif isinstance(kw.value, ast.Constant):
                kwargs.append(f"{kw.arg}={repr(kw.value.value)}")
            elif isinstance(kw.value, ast.Name):
                kwargs.append(f"{kw.arg}={kw.value.id}")
            else:
                kwargs.append(f"{kw.arg}=...")

        all_args = args + kwargs

        caller_id = caller_node.id

        # 尝试解析被调用者的完整ID
        resolved_id, resolved = self._resolve_callee(
            callee_name, call_node, file_path, caller_node, func_info
        )

        call_edge = CallEdge(
            caller_id=caller_id,
            callee_id=resolved_id,
            call_line=call_node.lineno,
            args=all_args,
            is_resolved=resolved,
            callee_name=callee_name,
        )
        calls.append(call_edge)

    def _get_call_name(self, func: ast.AST) -> str:
        """从函数调用表达式中提取函数名"""
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            # 方法调用：obj.method
            return func.attr
        elif isinstance(func, ast.Call):
            # 链式调用
            return self._get_call_name(func.func)
        return ''

    def _find_enclosing_function(self, node: ast.AST, file_path: str,
                                  functions: list[FunctionNode]) -> FunctionNode | None:
        """
        查找给定AST节点所属的最内层函数
        """
        target_line = node.lineno

        # 按定义位置层级匹配：最内层（起始行最大）的函数才是当前所在函数
        candidates = []
        for func in functions:
            # 函数定义本身的行不能算内部调用
            if func.line_start < target_line <= func.line_end:
                candidates.append(func)

        if not candidates:
            return None

        # 取起始行最大的（最内层函数）
        candidates.sort(key=lambda f: f.line_start, reverse=True)
        return candidates[0]

    def _resolve_callee(self, callee_name: str, call_node: ast.Call,
                         file_path: str, caller_node: FunctionNode,
                         func_info: dict) -> tuple[str, bool]:
        """
        尝试将函数名解析为完整的函数ID

        返回：
            (解析后的ID, 是否解析成功)
        """
        # 先尝试精确匹配（函数名相同）
        for fid, func in func_info.items():
            if func.name == callee_name:
                return fid, True

        # 尝试匹配类内部的方法
        method_candidates = []
        for fid, func in func_info.items():
            if func.name == callee_name:
                method_candidates.append(func)

        if len(method_candidates) == 1:
            return method_candidates[0].id, True

        # 匹配到多个同名的（不同类），检查当前调用是否在类内
        if method_candidates:
            if caller_node.class_name:
                # 优先匹配当前类内的方法
                for func in method_candidates:
                    if func.class_name == caller_node.class_name:
                        return func.id, True

                # 再匹配self.method()形式的调用
                if isinstance(call_node.func, ast.Attribute) and \
                   isinstance(call_node.func.value, ast.Name) and \
                   call_node.func.value.id == 'self':
                    for func in method_candidates:
                        if func.class_name == caller_node.class_name:
                            return func.id, True

            # 默认返回第一个匹配
            return method_candidates[0].id, True

        # 未解析 - 可能是外部函数
        return callee_name, False
