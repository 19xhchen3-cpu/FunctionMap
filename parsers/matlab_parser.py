"""MATLAB解析器 - 基于正则表达式"""

import os
import re

from models.function_node import FunctionNode
from models.call_edge import CallEdge
from parsers.base_parser import BaseParser


class MatlabParser(BaseParser):
    """
    MATLAB解析器

    由于没有成熟的开源MATLAB AST解析器，采用正则表达式实现。

    局限性:
    - 匿名函数 (@(x) ...) 不会被识别为独立的函数节点
    - classdef 语法支持有限
    - 局部函数的处理方式与独立函数一致
    """

    # MATLAB函数定义模式
    # function [out1, out2] = func_name(in1, in2)
    # function out_var = func_name(in1)
    # function func_name(in1)
    FUNC_DEF_PATTERN = re.compile(
        r'(?:^|\n)\s*'
        r'function\s+'                                # function 关键字
        r'(?:'                                         # 可选输出:
        r'\[([^\]]*)\]\s*=\s*|'                        #   [out1, out2] =
        r'([a-zA-Z]\w*)\s*=\s*'                       #   或 out_var =
        r')?'
        r'([a-zA-Z]\w*)\s*'                           # 函数名
        r'(?:\(([^)]*)\))?'                           # (in1, in2) (可选)
    )

    # 函数调用模式
    CALL_PATTERN = re.compile(
        r'(?<![\.\w\'\"])'                            # 前面不是 . 或单词字符
        r'([a-zA-Z]\w*)\s*'                           # 函数名
        r'\('                                          # ( 或没有括号
        r'([^()]*(?:\([^()]*\)[^()]*)*)'              # 参数
        r'\)'
    )

    # 需要排除的关键字
    KEYWORDS = frozenset({
        'if', 'elseif', 'else', 'for', 'while', 'switch', 'case', 'otherwise',
        'try', 'catch', 'end', 'return', 'break', 'continue',
        'global', 'persistent', 'parfor', 'spmd',
        'classdef', 'properties', 'methods', 'events', 'enumeration',
        'true', 'false', 'inf', 'nan', 'pi',
        'plot', 'disp', 'fprintf', 'sprintf', 'size', 'length', 'zeros', 'ones',
        'eye', 'rand', 'randn', 'linspace', 'logspace', 'reshape', 'repmat',
        'sum', 'mean', 'max', 'min', 'abs', 'sqrt', 'exp', 'log', 'sin', 'cos',
        'tan', 'asin', 'acos', 'atan', 'atan2', 'mod', 'rem',
    })

    # MATLAB内置函数（仅用于区分，不排除，但显示为未解析调用）
    BUILTINS = frozenset()

    def get_language(self) -> str:
        return 'matlab'

    def parse_file(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """解析MATLAB .m 文件"""

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
        except Exception as e:
            print(f"  警告: 无法读取文件 {file_path}: {e}")
            return [], []

        lines = source.split('\n')

        # 去除注释（% 开头的行）
        clean_source = self._remove_comments(source)
        clean_lines = clean_source.split('\n')

        functions: list[FunctionNode] = []
        calls: list[CallEdge] = []

        self._extract_functions(clean_source, clean_lines, file_path, functions)
        self._extract_calls(clean_source, clean_lines, source, lines, file_path, functions, calls)

        return functions, calls

    def _remove_comments(self, source: str) -> str:
        """
        去除MATLAB注释

        - % 到行末是注释
        - %{ ... %} 是块注释
        - 字符串内的 % 不是注释（用单引号包围的）
        """
        result = []
        i = 0
        in_string = False
        in_block_comment = False

        while i < len(source):
            # 处理字符串（单引号）
            if source[i] == "'" and not in_block_comment:
                if not in_string:
                    in_string = True
                else:
                    # 两个连续的单引号是转义
                    if i + 1 < len(source) and source[i + 1] == "'":
                        result.append("''")
                        i += 2
                        continue
                    in_string = False
                result.append(source[i])
                i += 1
                continue

            if in_block_comment:
                if source[i:i+2] == '%}':
                    in_block_comment = False
                    i += 2
                else:
                    result.append(' ')
                    i += 1
                continue

            # 块注释开始 %{
            if source[i:i+2] == '%{':
                in_block_comment = True
                result.append('  ')
                i += 2
                continue

            # 行注释 %（不在字符串内）
            if source[i] == '%' and not in_string:
                # 跳过到行末
                result.append(' ')
                i += 1
                while i < len(source) and source[i] != '\n':
                    result.append(' ')
                    i += 1
                continue

            result.append(source[i])
            i += 1

        return ''.join(result)

    def _extract_functions(self, clean_source: str, clean_lines: list[str],
                           file_path: str, functions: list[FunctionNode]) -> None:
        """提取函数定义"""
        for match in self.FUNC_DEF_PATTERN.finditer(clean_source):
            # group(3) 始终是函数名, group(4) 是参数列表(可选)
            func_name = match.group(3)
            if not func_name:
                continue
            params_str = match.group(4) or ''

            if func_name in self.KEYWORDS:
                continue

            start_line = clean_source[:match.start()].count('\n') + 1

            # 计算函数的结束行（找到匹配的 end 关键字）
            end_line = self._find_func_end(clean_source, start_line, clean_lines)

            # 提取参数
            params = []
            if params_str:
                params = [p.strip() for p in params_str.split(',') if p.strip()]

            # MATLAB文件名通常就是主函数名
            # 如果函数名与文件名相同，标记为主函数
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            if func_name == base_name:
                pass  # 主函数，无需特殊标记

            func_id = f"{file_path}::{func_name}"
            functions.append(FunctionNode(
                id=func_id,
                name=func_name,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                language='matlab',
                params=params,
            ))

    def _find_func_end(self, clean_source: str, func_start_line: int,
                       clean_lines: list[str]) -> int:
        """
        找到函数的结束行

        MATLAB用 end 关键字结束函数，但 end 也用于结束循环和条件语句。
        通过追踪嵌套层级来准确匹配。
        """
        lines = clean_source.split('\n')
        start_idx = func_start_line - 1

        # 统计从函数开始到各个 end 的层级
        depth = 1  # 进入函数定义
        for i in range(start_idx, len(lines)):
            line = lines[i].strip()

            # 跳过空行和注释（已去除）
            if not line:
                continue

            # 统计关键字
            # function, if, for, while, switch, try, parfor, spmd, classdef
            # 等会增加嵌套层级
            for kw in ('function ', 'if ', 'for ', 'while ', 'switch ',
                       'try ', 'parfor ', 'spmd ', 'classdef '):
                if line.startswith(kw) and i > start_idx:
                    # 简单检查不是字符串内
                    if kw not in ('for ',) or not line.startswith('for '):
                        pass
                    if not line.startswith('end'):
                        depth += 1

            if line == 'end':
                depth -= 1
                if depth == 0:
                    return i + 1
                if depth < 0:
                    # 出错了，恢复
                    depth = 0

        return len(lines)  # 默认到文件末尾

    def _extract_calls(self, clean_source: str, clean_lines: list[str],
                       source: str, lines: list[str],
                       file_path: str, functions: list[FunctionNode],
                       calls: list[CallEdge]) -> None:
        """提取函数调用"""
        # 先收集所有函数定义的范围，用于识别调用所在函数
        for match in self.CALL_PATTERN.finditer(clean_source):
            func_name = match.group(1)
            args_str = match.group(2)

            if func_name in self.KEYWORDS:
                continue

            if len(func_name) <= 1:
                continue

            call_line = clean_source[:match.start()].count('\n') + 1

            # 找到调用所在函数
            caller = self._find_enclosing_func(call_line, functions)
            if not caller:
                continue

            # 提取实参
            args = []
            if args_str:
                args = [a.strip()[:50] for a in args_str.split(',') if a.strip()]

            # 解析被调用函数
            resolved_id, resolved = self._resolve_func_name(func_name, functions)
            calls.append(CallEdge(
                caller_id=caller.id,
                callee_id=resolved_id,
                call_line=call_line,
                args=args,
                is_resolved=resolved,
                callee_name=func_name,
            ))

    def _find_enclosing_func(self, line: int, functions: list[FunctionNode]) -> FunctionNode | None:
        """查找包含某行代码的函数"""
        candidates = []
        for func in functions:
            if func.line_start < line <= func.line_end:
                candidates.append(func)
        if candidates:
            candidates.sort(key=lambda f: f.line_start, reverse=True)
            return candidates[0]
        return None

    def _resolve_func_name(self, name: str, functions: list[FunctionNode]) -> tuple[str, bool]:
        """根据函数名解析完整ID"""
        for func in functions:
            if func.name == name:
                return func.id, True
        return name, False
