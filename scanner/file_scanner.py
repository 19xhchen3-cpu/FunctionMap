"""文件扫描器：递归扫描文件夹，按扩展名识别源文件"""

import os

# 每种语言对应的文件扩展名映射
LANGUAGE_EXTENSIONS = {
    'python': {'.py'},
    'cpp': {'.cpp', '.cxx', '.cc', '.hpp', '.hxx', '.hh'},
    'c': {'.c', '.h'},
    'matlab': {'.m'},
    'ui': {'.ui'},  # Qt Designer 界面文件
}

# 扫描时跳过这些目录（精确名称匹配）
_SKIP_DIRS = frozenset({'node_modules', '__pycache__', '.git', '.svn', 'build', 'dist', 'deploy'})

# 最大文件大小（超过此大小的文件跳过不解析，防止大文件卡死）
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# 合并所有支持的扩展名，用于快速匹配
SUPPORTED_EXTENSIONS = set()
for exts in LANGUAGE_EXTENSIONS.values():
    SUPPORTED_EXTENSIONS.update(exts)


def detect_language(file_path: str) -> str | None:
    """根据文件扩展名检测编程语言"""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        if ext in exts:
            return lang
    return None


def scan_folder(folder_path: str) -> dict[str, list[str]]:
    """
    递归扫描文件夹，返回按语言分组的文件路径列表

    返回:
        {
            'python': ['path/to/file.py', ...],
            'cpp': ['path/to/file.cpp', ...],
            'c': ['path/to/file.c', ...],
            'matlab': ['path/to/file.m', ...],
        }
    """
    result: dict[str, list[str]] = {lang: [] for lang in LANGUAGE_EXTENSIONS}

    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"路径不存在或不是目录: {folder_path}")

    for root, dirs, files in os.walk(folder_path):
        # 跳过常见的非代码目录
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in _SKIP_DIRS]

        for file_name in files:
            file_path = os.path.join(root, file_name)
            # 跳过超大文件，防止卡死
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    print(f"  跳过超大文件（>{MAX_FILE_SIZE//1024//1024}MB）: {file_path}")
                    continue
            except OSError:
                continue
            lang = detect_language(file_name)
            if lang:
                result[lang].append(os.path.normpath(file_path))

    # 移除空的语言组
    return {k: v for k, v in result.items() if v}


def scan_files_flat(folder_path: str) -> list[tuple[str, str]]:
    """
    扫描文件夹，返回 (文件路径, 语言) 列表

    适用于需要顺序处理所有文件的场景
    """
    files: list[tuple[str, str]] = []

    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"路径不存在或不是目录: {folder_path}")

    for root, dirs, filenames in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in _SKIP_DIRS]

        for file_name in filenames:
            file_path = os.path.join(root, file_name)
            # 跳过超大文件，防止卡死
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            lang = detect_language(file_name)
            if lang:
                files.append((os.path.normpath(file_path), lang))

    return files
