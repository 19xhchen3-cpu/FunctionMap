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

    # 函数定义的正则模式 - 匹配标准函数定义
    # 格式: [返回类型] 函数名(参数列表) {
    FUNC_DEF_PATTERN: ClassVar[re.Pattern] = re.compile(
        r'(?:^|\n)\s*'                                          # 行开头
        r'(?:(?:inline|static|virtual|explicit|friend)\s+)*'     # 修饰符
        r'((?:[a-zA-Z_]\w*\s*(?:<[^>]*>)?\s*(?:\s*&|\s*\*)?\s*' # 返回类型
        r'(?:\s+[a-zA-Z_]\w*)?(?:\s*::\s*[a-zA-Z_]\w*)?\s*'    # 命名空间::类型
        r'(?:\s*<[^>]*>)?(?:\s*&|\s*\*)?\s*)*?)'                # 模板参数
        r'([a-zA-Z_~]\w*)\s*'                                   # 函数名（含析构~）
        r'\('                                                   # 参数列表开始
        r'([^)]*?)'                                             # 参数列表内容
        r'\)\s*'                                                # 参数列表结束
        r'(?:const\s+)?(?:override\s+)?(?:final\s+)?'           # C++修饰符
        r'(?:throw\s*\([^)]*\)\s*)?'                           # 异常声明
        r'(?:=\s*(?:0|delete|default)\s*)?'                    # 纯虚/删除/默认
        r'(?:\{|;)'                                              # 函数体开始或声明
    )

    # 函数调用模式
    CALL_PATTERN: ClassVar[re.Pattern] = re.compile(
        r'(?<![\.\w])'                      # 前面不是 . 或单词字符
        r'([a-zA-Z_]\w*)\s*'                # 函数名
        r'\('                               # 开始括号
        r'([^()]*(?:\([^()]*\)[^()]*)*)'    # 参数（支持嵌套括号）
        r'\)'                               # 结束括号
    )

    # 需要排除的关键字（不是函数名）
    KEYWORDS: ClassVar[frozenset] = frozenset({
        'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'return',
        'sizeof', 'typedef', 'throw', 'catch', 'try', 'new', 'delete',
        'class', 'struct', 'enum', 'union', 'namespace', 'template',
        'typename', 'const', 'constexpr', 'static_cast', 'dynamic_cast',
        'reinterpret_cast', 'const_cast', 'typeid', 'decltype',
        'ifdef', 'ifndef', 'endif', 'define', 'include', 'pragma',
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
        """使用正则表达式解析C/C++文件"""
        source = self._read_source(file_path)
        if source is None:
            return [], []

        language = self.detect_c_vs_cpp(file_path)
        lines = source.split('\n')

        # 去除注释和字符串后的源码
        clean_source = self._strip_comments_and_strings(source)
        clean_lines = clean_source.split('\n')

        functions: list[FunctionNode] = []
        calls: list[CallEdge] = []

        self._regex_extract_functions(clean_source, clean_lines, file_path, language, functions)
        self._regex_extract_calls(clean_source, clean_lines, source, lines, file_path, functions, calls)

        return functions, calls

    def _regex_extract_functions(self, clean_source: str, clean_lines: list[str],
                                  file_path: str, language: str,
                                  functions: list[FunctionNode]) -> None:
        """用正则提取函数定义"""
        # 用更精确的模式匹配函数定义
        # 模式: 先找 { 和 ; 确定块范围，再往前找函数名
        func_name_pattern = re.compile(
            r'(?:^|\n)\s*'
            r'(?:(?:inline|static|virtual|explicit|friend|constexpr)\s+)*'
            r'(?:[a-zA-Z_]\w*(?:\s*<[^>]*>)?\s*(?:\s*&|\s*\*)?\s*'
            r'(?:\s+[a-zA-Z_]\w*)?(?:\s*::\s*[a-zA-Z_]\w*)?\s*'
            r'(?:\s*<[^>]*>)?(?:\s*&|\s*\*)?\s*)*?'
            r'([a-zA-Z_~]\w*)\s*'
            r'\('
            r'([^)]*?)'
            r'\)\s*'
            r'(?:const\s+)?(?:override\s+)?(?:final\s+)?'
            r'(?:throw\s*\([^)]*\)\s*)?'
            r'(?:=\s*(?:0|delete|default)\s*)?'
            r'\s*(\{|;)'
        )

        seen_funcs: set[tuple[str, int]] = set()  # (func_name, start_line)

        for match in func_name_pattern.finditer(clean_source):
            func_name = match.group(1)
            params_str = match.group(2).strip()
            brace = match.group(3)

            # 过滤关键字
            if func_name in self.KEYWORDS:
                continue

            # 过滤类型名（如 int, char 等作为函数名）
            if func_name in self.TYPE_KEYWORDS:
                continue

            # 过滤构造/析构前的不完整匹配
            if func_name == 'if' or func_name == 'else':
                continue

            # 检查匹配位置前面的上下文
            # 如果函数名前有 =, return, case 等，说明是赋值或返回语句，不是定义
            pre_context = clean_source[max(0, match.start() - 30):match.start()]
            if re.search(r'[=,]\s*$', pre_context):
                continue
            if re.search(r'(return|case|throw|goto)\s+$', pre_context):
                continue

            # 过滤已知的C库函数（它们不可能是定义）
            if func_name in ('printf', 'scanf', 'fprintf', 'sprintf', 'fscanf',
                             'malloc', 'free', 'calloc', 'realloc', 'memcpy',
                             'memmove', 'memset', 'strcpy', 'strlen', 'strcmp',
                             'sizeof', 'assert', 'exit', 'atoi', 'atof', 'abs',
                             'sqrt', 'pow', 'sin', 'cos', 'tan', 'log', 'exp',
                             'fabs', 'ceil', 'floor', 'round'):
                continue

            # 计算行号
            start_pos = match.start()
            start_line = clean_source[:start_pos].count('\n') + 1

            # 去重：同一函数名在相同位置定义
            if (func_name, start_line) in seen_funcs:
                continue
            seen_funcs.add((func_name, start_line))

            # 计算结束行号
            end_line = start_line
            if brace == '{':
                # 尝试匹配对应的 }
                start_brace_pos = match.end() - 1  # { 的位置
                brace_count = 1
                pos = start_brace_pos + 1
                while pos < len(clean_source) and brace_count > 0:
                    if clean_source[pos] == '{':
                        brace_count += 1
                    elif clean_source[pos] == '}':
                        brace_count -= 1
                    pos += 1
                if brace_count == 0:
                    end_line = clean_source[:pos].count('\n') + 1

            # 提取参数名
            params = self._extract_params(params_str)

            func_id = f"{file_path}::{func_name}"
            functions.append(FunctionNode(
                id=func_id,
                name=func_name,
                file_path=file_path,
                line_start=start_line,
                line_end=end_line,
                language=language,
                params=params,
            ))

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

    def _regex_extract_calls(self, clean_source: str, clean_lines: list[str],
                              source: str, lines: list[str],
                              file_path: str,
                              functions: list[FunctionNode],
                              calls: list[CallEdge]) -> None:
        """用正则提取函数调用"""
        for match in self.CALL_PATTERN.finditer(clean_source):
            func_name = match.group(1)
            args_str = match.group(2)

            # 过滤关键字
            if func_name in self.KEYWORDS:
                continue
            if func_name in self.TYPE_KEYWORDS:
                continue

            # 过滤过短的匹配
            if len(func_name) == 1:
                continue

            # 找到所在函数
            call_line = clean_source[:match.start()].count('\n') + 1
            caller = self._find_enclosing_func_regex(call_line, functions)
            if not caller:
                continue

            # 提取实参
            args = self._extract_call_args(args_str)

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
