#!/usr/bin/env python3
"""
FunctionMap 构建脚本 — 打包为独立可执行文件

用法:
    python build.py                  # 构建当前平台的可执行文件
    python build.py --onefile        # 构建为单个 exe 文件（仅 Windows）
    python build.py --clean          # 先清理旧的构建产物再构建

构建产物:
    Windows: dist/FunctionMap/FunctionMap.exe
    macOS:   dist/FunctionMap.app
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.absolute()
SPEC_FILE = PROJECT_ROOT / "functionmap.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def check_pyinstaller() -> bool:
    """检查 PyInstaller 是否已安装"""
    try:
        import PyInstaller  # noqa
        return True
    except ImportError:
        return False


def install_pyinstaller():
    """安装 PyInstaller"""
    print("正在安装 PyInstaller...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "pyinstaller"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    print("PyInstaller 安装完成\n")


def clean_build():
    """清理旧的构建产物"""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            print(f"  清理: {d}")
            shutil.rmtree(d)
    # 清理 PyInstaller 自动生成的同名 spec 文件
    # 注意：Windows 大小写不敏感，只删自动生成的 (以入口名命名)
    for p in PROJECT_ROOT.glob("*.spec"):
        if p.name.lower() != "functionmap.spec":  # 不删我们自己的 spec
            print(f"  清理自动生成: {p.name}")
            p.unlink(missing_ok=True)
    # 也清理 __pycache__
    for p in PROJECT_ROOT.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    print("  清理完成\n")


def run_pyinstaller(onefile: bool = False):
    """运行 PyInstaller 打包"""
    # 构建命令
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC_FILE)]

    if onefile:
        # --onefile 与 .spec 文件不兼容，需要额外处理
        # 这里改为直接传参模式
        print("  --onefile 模式: 使用纯命令行参数（不使用 .spec 文件）")
        cmd = _build_onefile_cmd()

    print(f"运行: {' '.join(cmd)}\n")
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT), stdout=sys.stdout, stderr=sys.stderr)


def _build_onefile_cmd() -> list[str]:
    """构建单文件模式的 PyInstaller 命令"""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "FunctionMap",
        "--add-data", f"web/templates/index.html{os.pathsep}web/templates",
        "--add-data", f"web/static/app.js{os.pathsep}web/static",
        "--add-data", f"web/static/style.css{os.pathsep}web/static",
        # 隐藏导入
    ]
    hidden = [
        "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.loops.asyncio", "uvicorn.protocols", "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.middleware", "uvicorn.middleware.asgi2", "uvicorn.middleware.wsgi",
        "uvicorn.middleware.proxy_headers", "uvicorn.lifespan", "uvicorn.lifespan.on",
        "uvicorn.lifespan.off", "uvicorn._normalize",
        "fastapi", "fastapi.routing", "fastapi.openapi", "fastapi.openapi.utils",
        "starlette", "starlette.applications", "starlette.routing",
        "starlette.middleware", "starlette.middleware.errors", "starlette.middleware.base",
        "starlette.requests", "starlette.responses", "starlette.staticfiles",
        "starlette.templating", "starlette.websockets",
        "pydantic", "pydantic.dataclasses", "pydantic.types", "pydantic.fields",
        "networkx", "networkx.algorithms", "networkx.drawing",
        "jinja2", "jinja2.ext", "yaml", "multipart",
    ]
    for h in hidden:
        cmd.extend(["--hidden-import", h])

    # 排除
    excludes = ["test", "unittest", "distutils", "setuptools", "pip",
                 "matplotlib", "numpy", "scipy", "PIL", "pandas"]
    for e in excludes:
        cmd.extend(["--exclude-module", e])

    cmd.append(str(PROJECT_ROOT / "main.py"))
    return cmd


def print_summary():
    """打印构建完成摘要"""
    print()
    print("=" * 60)
    print("  FunctionMap 打包完成！")
    print("=" * 60)
    print()

    # 查找生成的可执行文件
    if sys.platform == "win32":
        exe_path = DIST_DIR / "FunctionMap" / "FunctionMap.exe"
        if exe_path.exists():
            print(f"  可执行文件: {exe_path}")
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"  文件大小: {size_mb:.1f} MB")
            print()
            print(f"  运行: {exe_path}")
            print(f"  或: {exe_path} --path D:/projects/mycode")
    elif sys.platform == "darwin":
        app_path = DIST_DIR / "FunctionMap.app"
        if app_path.exists():
            print(f"  应用包: {app_path}")
            print()
            print(f"  运行: open {app_path}")
            print(f"  或: {DIST_DIR / 'FunctionMap' / 'FunctionMap'} --path /path/to/code")
    else:
        exe_path = DIST_DIR / "FunctionMap" / "FunctionMap"
        if exe_path.exists():
            print(f"  可执行文件: {exe_path}")
            print()
            print(f"  运行: {exe_path}")
            print(f"  或: {exe_path} --path /path/to/code")

    print()
    print("  命令行选项:")
    print("    --path PATH    启动后自动扫描指定目录")
    print("    --port PORT    指定端口（默认 8000）")
    print("    --no-open      不自动打开浏览器")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="FunctionMap 构建脚本 — 打包为独立可执行文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build.py                 # 打包为文件夹模式
  python build.py --onefile       # 打包为单个 exe（仅 Windows）
  python build.py --clean         # 清理后打包
        """,
    )
    parser.add_argument("--onefile", action="store_true",
                        help="打包为单个 exe 文件（仅 Windows，macOS 不适用）")
    parser.add_argument("--clean", action="store_true",
                        help="先清理旧的构建产物")
    parser.add_argument("--no-install", action="store_true",
                        help="不自动安装 PyInstaller，缺少时直接报错")

    args = parser.parse_args()

    # ── 检查 / 安装 PyInstaller ──
    if not check_pyinstaller():
        if args.no_install:
            print("错误: 需要 PyInstaller，请先执行: pip install pyinstaller")
            sys.exit(1)
        install_pyinstaller()

    # ── 可选清理 ──
    if args.clean:
        print("清理旧的构建产物...")
        clean_build()

    # ── 打包 ──
    print("开始打包 FunctionMap...")
    print(f"  平台: {sys.platform}")
    print(f"  Python: {sys.version}")
    print(f"  模式: {'单文件' if args.onefile else '文件夹'}")
    print()

    run_pyinstaller(onefile=args.onefile)

    # ── 结果摘要 ──
    print_summary()


if __name__ == "__main__":
    main()
