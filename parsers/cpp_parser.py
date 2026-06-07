"""C/C++解析器 - 基于正则表达式解析（可选tree-sitter支持）"""

import os
import re
from typing import ClassVar

from models.function_node import FunctionNode
from models.call_edge import CallEdge
from parsers.base_parser import BaseParser


class CppParser(BaseParser):
    """
    C/C++解析器

    实现策略:
    1. 首选方案：tree-sitter（需安装 tree-sitter-cpp/tree-sitter-c 库）
    2. 兜底方案：基于正则表达式的解析（无需额外依赖，适用于常见场景）

    正则方案限制：
    - 函数指针、模板元编程等高级语法可能误判
    - 宏展开无法解析
    - 重载函数仅解析函数名，不处理参数类型差异
    """

    # 函数定义的正则模式 - 仅匹配 返回类型 [类名::]函数名(
    # 参数和 { 由调用方用 _find_matching_paren 跨行查找，避免多行正则卡死
    FUNC_DEF_PATTERN: ClassVar[re.Pattern] = re.compile(
        r'^\s*'                                                 # 行开头 + 缩进
        r'(?:(?:inline|static|virtual|explicit|friend|constexpr)\s+)*'
        r'(?:[a-zA-Z_]\w*(?:\s*<[^>]*>)?\s*(?:\s*&|\s*\*)?\s*)' # 返回类型（必选，至少一个）
        r'(?:[a-zA-Z_]\w*\s*::\s*)?'                            # 可选 类名::
        r'([a-zA-Z_~]\w*)\s*'                                   # 函数名（含析构~）
        r'\('                                                   # ( 开始
    )

    # 函数定义正则 - 宽松版，匹配 类名::函数名( 或 ~函数名(
    FUNC_DEF_LAX_PATTERN: ClassVar[re.Pattern] = re.compile(
        r'^\s*'
        r'(?:(?:inline|static|virtual|explicit|friend|constexpr)\s+)*'
        r'(?:[a-zA-Z_]\w*\s*::\s*)?'                            # 可选 类名::
        r'([a-zA-Z_~]\w*)\s*'                                   # 函数名
        r'\('
    )

    # 函数调用模式 - 单行匹配
    CALL_PATTERN: ClassVar[re.Pattern] = re.compile(
        r'(?<![\.\w])'
        r'([a-zA-Z_]\w*)\s*'
        r'\('
    )

    # 需要排除的关键字（不是函数名）
    KEYWORDS: ClassVar[frozenset] = frozenset({
        'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'return',
        'sizeof', 'typedef', 'throw', 'catch', 'try', 'new', 'delete',
        'class', 'struct', 'enum', 'union', 'namespace', 'template',
        'typename', 'const', 'constexpr', 'static_cast', 'dynamic_cast',
        'reinterpret_cast', 'const_cast', 'typeid', 'decltype',
        'ifdef', 'ifndef', 'endif', 'define', 'include', 'pragma',
        # Qt 框架关键字/宏（防止被误识别为函数名）
        'emit', 'signals', 'slots', 'qobject_cast',
        'SIGNAL', 'SLOT',
        'Q_DECLARE_METATYPE', 'Q_ENUM', 'Q_FLAG', 'Q_INVOKABLE',
    })

    # 简单类型关键字（匹配类型时视为类型而非函数名）
    TYPE_KEYWORDS: ClassVar[frozenset] = frozenset({
        'int', 'char', 'float', 'double', 'void', 'bool', 'long',
        'short', 'unsigned', 'signed', 'size_t', 'auto',
    })

    def __init__(self):
        self._use_tree_sitter = False
        self._try_init_tree_sitter()

    def _try_init_tree_sitter(self):
        """尝试初始化tree-sitter"""
        try:
            import tree_sitter_cpp as tscpp
            import tree_sitter_c as tsc
            from tree_sitter import Language, Parser
            self._ts_lang_cpp = Language(tscpp.language())
            self._ts_lang_c = Language(tsc.language())
            self._ts_parser_cpp = Parser(self._ts_lang_cpp)
            self._ts_parser_c = Parser(self._ts_lang_c)
            self._use_tree_sitter = True
        except ImportError:
            self._use_tree_sitter = False

    def get_language(self) -> str:
        return 'cpp'

    def detect_c_vs_cpp(self, file_path: str) -> str:
        """根据扩展名判断是C还是C++"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.c',):
            return 'c'
        return 'cpp'

    def parse_file(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """解析C/C++文件"""
        if self._use_tree_sitter:
            try:
                return self._parse_with_tree_sitter(file_path)
            except Exception as e:
                print(f"  tree-sitter解析失败，切换到正则模式: {e}")

        return self._parse_with_regex(file_path)

    def _read_source(self, file_path: str) -> str | None:
        """读取源文件，处理编码"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            print(f"  警告: 无法读取文件 {file_path}: {e}")
            return None

    def _strip_comments_and_strings(self, source: str) -> str:
        """
        去除注释和字符串字面量，避免在注释/字符串中误匹配

        返回一个新的字符串，注释/字符串被替换为等长空格
        """
        result = list(source)
        i = 0
        in_single_quote = False
        in_double_quote = False

        while i < len(source):
            # 行注释 //
            if source[i:i+2] == '//' and not in_single_quote and not in_double_quote:
                end = source.find('\n', i)
                if end == -1:
                    end = len(source)
                for j in range(i, end):
                    result[j] = ' '
                i = end
                continue

            # 块注释 /* */
            if source[i:i+2] == '/*' and not in_single_quote and not in_double_quote:
                end = source.find('*/', i + 2)
                if end == -1:
                    end = len(source)
                else:
                    end += 2
                for j in range(i, end):
                    result[j] = ' '
                i = end
                continue

            # 预处理指令 #include, #define 等
            if source[i] == '#' and not in_single_quote and not in_double_quote:
                end = source.find('\n', i)
                if end == -1:
                    end = len(source)
                for j in range(i, end):
                    result[j] = ' '
                i = end
                continue

            # 字符串字面量
            if source[i] == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif source[i] == "'" and not in_double_quote:
                # 处理字符字面量 'x' 和字符转义 '\\'
                if not in_single_quote:
                    in_single_quote = True
                else:
                    # 简单字符字面量结束
                    in_single_quote = False

            i += 1

        return ''.join(result)

    def _parse_with_tree_sitter(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """使用tree-sitter解析"""
        source = self._read_source(file_path)
        if source is None:
            return [], []

        language = self.detect_c_vs_cpp(file_path)
        parser = self._ts_parser_cpp if language == 'cpp' else self._ts_parser_c
        tree = parser.parse(bytes(source, 'utf-8'))
        root = tree.root_node

        functions: list[FunctionNode] = []
        calls: list[CallEdge] = []

        # 提取函数定义
        self._ts_extract_functions(root, source.split('\n'), file_path, language, functions)

        # 提取函数调用
        self._ts_extract_calls(root, file_path, source, functions, calls)

        return functions, calls

    def _ts_extract_functions(self, node, lines, file_path, language, functions):
        """从tree-sitter AST中提取函数定义"""
        if node.type in ('function_definition',):
            # 获取函数声明符
            declarator = None
            for child in node.children:
                if child.type == 'function_declarator':
                    declarator = child
                    break
                # 有时前有指针修饰符
                if child.type == 'pointer_declarator':
                    # 查找内部的function_declarator
                    d = child
                    for c in d.children:
                        if c.type == 'function_declarator':
                            declarator = c
                            break

            if declarator:
                # 提取函数名
                func_name_node = None
                params = []
                for child in declarator.children:
                    if child.type in ('identifier', 'field_identifier'):
                        func_name_node = child
                    elif child.type == 'parameter_list':
                        for param in child.children:
                            if param.type == 'parameter_declaration':
                                param_name = self._ts_get_param_name(param)
                                if param_name:
                                    params.append(param_name)
                            elif param.type == 'variadic_parameter':
                                params.append('...')

                if func_name_node:
                    func_name = source_bytes = func_name_node.text.decode() if hasattr(func_name_node, 'text') else ''
                    if isinstance(func_name, bytes):
                        func_name = func_name.decode('utf-8', errors='replace')

                    func_id = f"{file_path}::{func_name}"
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    functions.append(FunctionNode(
                        id=func_id,
                        name=func_name,
                        file_path=file_path,
                        line_start=start_line,
                        line_end=end_line,
                        language=language,
                        params=params,
                    ))

        # 递归子节点
        for child in node.children:
            self._ts_extract_functions(child, lines, file_path, language, functions)

    def _ts_get_param_name(self, param_node) -> str:
        """从tree-sitter参数声明节点中提取参数名"""
        for child in param_node.children:
            if child.type == 'identifier':
                return child.text.decode() if isinstance(child.text, bytes) else child.text
        return ''

    def _ts_extract_calls(self, node, file_path, source, functions, calls):
        """从tree-sitter AST中提取函数调用"""
        if node.type == 'call_expression':
            # 获取函数名
            func_name = ''
            func_node = node.children[0] if node.children else None
            if func_node:
                if func_node.type == 'identifier':
                    t = func_node.text
                    func_name = t.decode() if isinstance(t, bytes) else t
                elif func_node.type == 'field_expression':
                    # obj.method
                    t = func_node.children[-1].text if func_node.children else b''
                    func_name = t.decode() if isinstance(t, bytes) else t

            if func_name and func_name not in self.KEYWORDS:
                # 找到所在函数
                caller = self._find_enclosing_func_ts(node, file_path, functions)
                if caller:
                    # 收集参数
                    args = []
                    arg_list = None
                    for child in node.children:
                        if child.type == 'argument_list':
                            arg_list = child
                            break
                    if arg_list:
                        for arg in arg_list.children:
                            if arg.type == 'identifier':
                                t = arg.text
                                args.append(t.decode() if isinstance(t, bytes) else t)
                            elif arg.type == 'number_literal':
                                t = arg.text
                                args.append(t.decode() if isinstance(t, bytes) else t)
                            elif arg.type == 'string_literal':
                                args.append('"..."')

                    resolved_id, resolved = self._resolve_func_name(func_name, functions)
                    calls.append(CallEdge(
                        caller_id=caller.id,
                        callee_id=resolved_id,
                        call_line=node.start_point[0] + 1,
                        args=args,
                        is_resolved=resolved,
                        callee_name=func_name,
                    ))

        for child in node.children:
            self._ts_extract_calls(child, file_path, source, functions, calls)

    def _find_enclosing_func_ts(self, node, file_path, functions) -> FunctionNode | None:
        """查找包含某节点的函数（tree-sitter版本）"""
        target_start = node.start_point[0]
        candidates = []
        for func in functions:
            if func.line_start < target_start <= func.line_end:
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

    def _parse_with_regex(self, file_path: str) -> tuple[list[FunctionNode], list[CallEdge]]:
        """使用逐行解析方法提取C/C++函数定义和调用（避免正则回溯卡死）"""
        source = self._read_source(file_path)
        if source is None:
            return [], []

        language = self.detect_c_vs_cpp(file_path)
        lines = source.split('\n')

        # 去除注释和字符串后的源码
        clean_source = self._strip_comments_and_strings(source)
        clean_lines = clean_source.split('\n')

        # 预处理：移除 Qt Q_PROPERTY 宏，防止误匹配
        clean_source = re.sub(r'Q_PROPERTY\s*\([^)]*\)\s*', '', clean_source)
        clean_lines = clean_source.split('\n')

        functions: list[FunctionNode] = []
        calls: list[CallEdge] = []

        # 第一阶段：逐行提取函数定义
        self._line_based_extract_functions(clean_lines, source.split('\n'), file_path, language, functions)
        if not functions:
            return [], []

        # 第二阶段：在函数体内提取调用
        self._line_based_extract_calls(clean_lines, source.split('\n'), file_path, functions, calls)

        return functions, calls

    def _find_matching_paren(self, lines: list[str], start_lineno: int, start_col: int) -> tuple[int, int] | None:
        """
        从 (start_lineno, start_col) 开始找到匹配的 )。
        支持跨行和嵌套括号。
        返回 (行号, 列号) 或 None。
        """
        depth = 1
        lineno = start_lineno
        col = start_col
        while lineno < len(lines):
            line = lines[lineno]
            while col < len(line):
                ch = line[col]
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        return lineno, col
                col += 1
            lineno += 1
            col = 0
        return None

    def _line_based_extract_functions(self, clean_lines: list[str], lines: list[str],
                                       file_path: str, language: str,
                                       functions: list[FunctionNode]) -> None:
        """
        逐行扫描提取函数定义。

        用正则匹配单行的函数名+( 模式，然后用 _find_matching_paren 跨行
        查找匹配的 ) 和 {，避免多行正则回溯。
        """
        seen_funcs: set[tuple[str, int]] = set()

        for lineno in range(len(clean_lines)):
            line = clean_lines[lineno]
            if not line.strip():
                continue

            for pattern, has_return_type in [(self.FUNC_DEF_PATTERN, True),
                                              (self.FUNC_DEF_LAX_PATTERN, False)]:
                match = pattern.match(line)
                if not match:
                    continue

                func_name = match.group(1)

                # ----- 过滤器 -----
                if func_name in self.KEYWORDS or func_name in self.TYPE_KEYWORDS:
                    continue
                if len(func_name) <= 1:
                    continue

                # 上下文：前面不能有 = , . { return case throw goto
                # 如果前面有 {，说明在代码块内部（lambda 等），不是函数定义
                pre_context = line[:match.start()]
                if re.search(r'[=,.]\s*$', pre_context):
                    continue
                if re.search(r'(return|case|throw|goto)\s+$', pre_context):
                    continue
                if pre_context.strip().endswith(('&', '*', 'const', 'mutable')):
                    continue
                if '{' in pre_context:
                    continue

                # 库函数过滤
                if func_name in ('printf', 'scanf', 'fprintf', 'sprintf', 'fscanf',
                                 'malloc', 'free', 'calloc', 'realloc', 'memcpy',
                                 'memmove', 'memset', 'strcpy', 'strlen', 'strcmp',
                                 'assert', 'exit', 'atoi', 'atof', 'abs',
                                 'sqrt', 'pow', 'sin', 'cos', 'tan', 'log', 'exp',
                                 'fabs', 'ceil', 'floor', 'round',
                                 'connect', 'disconnect', 'emit'):
                    continue

                # 变量声明检测：TypeName variableName(args) 模式
                if has_return_type:
                    text_before_func = match.group(0)[:match.group(0).find(func_name)]
                    # 如果函数名前有 ::，说明是限定名（ClassName::funcName），跳过检测
                    if '::' not in text_before_func:
                        rt_words = text_before_func.strip().split()
                        if (rt_words and rt_words[-1][0].isupper()
                                and func_name[0].islower()):
                            continue

                # 找到本行第一个 (
                open_paren_idx = line.find('(', match.start())
                if open_paren_idx == -1:
                    continue

                # 找匹配的 )
                paren = self._find_matching_paren(clean_lines, lineno, open_paren_idx + 1)
                if paren is None:
                    continue
                close_lineno, close_col = paren

                # 从 ) 后面往前最多找 5 行看有没有 {
                found_brace = False
                brace_lineno = close_lineno
                for scan in range(5):
                    scan_line = close_lineno + scan
                    if scan_line >= len(clean_lines):
                        break
                    if scan == 0:
                        text = clean_lines[scan_line][close_col:]
                    else:
                        text = clean_lines[scan_line]
                    # 确保 { 不是出现在 lambda [] 或 () 或 {} 内部
                    brace_pos = text.find('{')
                    if brace_pos >= 0:
                        # 检查这个 { 之前的文本：如果括号深度 > 0，说明 { 在表达式内部
                        text_before = text[:brace_pos]
                        opens = text_before.count('(') + text_before.count('[') + text_before.count('{')
                        closes = text_before.count(')') + text_before.count(']') + text_before.count('}')
                        if opens <= closes:
                            found_brace = True
                            brace_lineno = scan_line
                            break

                if not found_brace:
                    continue

                # 6. 检查是否在已找到的函数体内（排除函数调用被误识别为定义）
                inside_existing = False
                for existing in functions:
                    if existing.line_start < lineno + 1 <= existing.line_end:
                        inside_existing = True
                        break
                if inside_existing:
                    continue

                # 7. 关键检测：如果参数文本中包含 {（lambda），说明这是函数调用而非定义
                # 提取参数文本并检查
                if close_lineno == lineno:
                    param_check = line[open_paren_idx + 1:close_col]
                else:
                    param_parts = [line[open_paren_idx + 1:]]
                    for pl in range(lineno + 1, close_lineno):
                        param_parts.append(clean_lines[pl])
                    param_parts.append(clean_lines[close_lineno][:close_col])
                    param_check = ' '.join(param_parts)
                if '{' in param_check:
                    continue

                # 去重
                if (func_name, lineno + 1) in seen_funcs:
                    continue
                seen_funcs.add((func_name, lineno + 1))

                # 计算函数结束行号
                end_line = self._find_block_end(clean_lines, brace_lineno, lineno + 1)

                # 提取参数名（跨行时拼接）
                if close_lineno == lineno:
                    param_text = line[open_paren_idx + 1:close_col]
                else:
                    parts = [line[open_paren_idx + 1:]]
                    for pl in range(lineno + 1, close_lineno):
                        parts.append(clean_lines[pl])
                    parts.append(clean_lines[close_lineno][:close_col])
                    param_text = ' '.join(parts)
                params = self._extract_params(param_text)

                func_id = f"{file_path}::{func_name}"
                functions.append(FunctionNode(
                    id=func_id,
                    name=func_name,
                    file_path=file_path,
                    line_start=lineno + 1,
                    line_end=end_line,
                    language=language,
                    params=params,
                ))
                break  # pattern loop

    def _find_block_end(self, lines: list[str], brace_line: int, fallback: int) -> int:
        """从 { 所在行开始，找到匹配的 } 行号（1-indexed）"""
        brace_count = 0
        found_open = False
        for lineno in range(brace_line, len(lines)):
            for ch in lines[lineno]:
                if ch == '{':
                    brace_count += 1
                    found_open = True
                elif ch == '}':
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        return lineno + 1
        return fallback

    def _line_based_extract_calls(self, clean_lines: list[str], lines: list[str],
                                   file_path: str, functions: list[FunctionNode],
                                   calls: list[CallEdge]) -> None:
        """
        在已识别的函数体内逐行提取调用关系。
        对每个函数，扫描其行范围，用简单正则找到 name( 模式，
        然后用括号平衡匹配提取完整参数。
        """
        for func in functions:
            func_start = func.line_start - 1  # 0-indexed
            func_end = min(func.line_end, len(clean_lines))

            for lineno in range(func_start, func_end):
                line = clean_lines[lineno]
                if not line.strip():
                    continue

                # 使用简单正则找所有 name( 模式
                for match in self.CALL_PATTERN.finditer(line):
                    callee_name = match.group(1)
                    call_col = match.end()  # 位置在 ( 之后

                    # 过滤关键字
                    if callee_name in self.KEYWORDS or callee_name in self.TYPE_KEYWORDS:
                        continue
                    if len(callee_name) <= 1:
                        continue

                    # 找到匹配的 )
                    result = self._find_matching_paren(clean_lines, lineno, call_col)
                    if result is None:
                        continue

                    # 提取参数文本
                    end_lineno, end_col = result
                    if end_lineno == lineno:
                        args_str = line[call_col:end_col]
                    else:
                        parts = [line[call_col:]]
                        for al in range(lineno + 1, end_lineno):
                            parts.append(clean_lines[al])
                        parts.append(clean_lines[end_lineno][:end_col])
                        args_str = ','.join(parts)

                    # 解析参数
                    args = self._extract_call_args(args_str)

                    resolved_id, resolved = self._resolve_func_name(callee_name, functions)
                    calls.append(CallEdge(
                        caller_id=func.id,
                        callee_id=resolved_id,
                        call_line=lineno + 1,
                        args=args,
                        is_resolved=resolved,
                        callee_name=callee_name,
                    ))

    def _find_enclosing_func_regex(self, line: int, functions: list[FunctionNode]) -> FunctionNode | None:
        """查找包含某行代码的函数"""
        candidates = []
        for func in functions:
            if func.line_start < line <= func.line_end:
                candidates.append(func)
        if candidates:
            candidates.sort(key=lambda f: f.line_start, reverse=True)
            return candidates[0]
        return None

    def _extract_call_args(self, args_str: str) -> list[str]:
        """从调用参数串中提取实参"""
        if not args_str:
            return []

        args = []
        depth = 0
        current = ''
        for ch in args_str:
            if ch == ',' and depth == 0:
                arg = current.strip()
                if arg:
                    args.append(arg[:50])  # 截断长表达式
                current = ''
            elif ch in '({[':
                depth += 1
                current += ch
            elif ch in ')}]':
                depth -= 1
                current += ch
            else:
                current += ch

        arg = current.strip()
        if arg:
            args.append(arg[:50])

        return args

    def _extract_params(self, params_str: str) -> list[str]:
        """从参数列表中提取参数名"""
        if not params_str or params_str == 'void':
            return []

        # 按逗号分割参数
        params = []
        depth = 0
        current = ''
        for ch in params_str:
            if ch == ',' and depth == 0:
                param = current.strip()
                if param:
                    # 提取最后一个单词作为参数名
                    parts = param.split()
                    if parts:
                        # 处理 int* x, char **argv, int& ref 等
                        name = parts[-1].lstrip('*&')
                        if name and not name.startswith(('int', 'char', 'float', 'double', 'void', 'long',
                                                          'short', 'unsigned', 'signed', 'const', 'auto')):
                            params.append(name)
                        else:
                            # 只有类型没有变量名的情况
                            params.append('')
                current = ''
            elif ch in '({[':
                depth += 1
                current += ch
            elif ch in ')}]':
                depth -= 1
                current += ch
            else:
                current += ch

        # 最后一个参数
        param = current.strip()
        if param:
            parts = param.split()
            if parts:
                name = parts[-1].lstrip('*&')
                if name and not name.startswith(('int', 'char', 'float', 'double', 'void', 'long',
                                                  'short', 'unsigned', 'signed', 'const', 'auto')):
                    params.append(name)
                else:
                    params.append('')

        return [p for p in params if p]
