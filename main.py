#!/usr/bin/env python3
"""
FunctionMap - 代码函数调用关系可视化工具

用法:
    python main.py                    # 启动Web服务器（默认端口8000）
    python main.py --port 8080        # 指定端口
    python main.py --host 0.0.0.0     # 监听所有网络接口
    python main.py --path /tmp/mycode # 启动后直接扫描指定目录
"""

import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _free_port(port: int):
    """释放指定端口（杀掉占用进程）"""
    import subprocess
    import platform

    if platform.system() != 'Windows':
        return  # 仅Windows需要此处理

    try:
        result = subprocess.run(
            ['netstat', '-ano'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                pid = line.strip().split()[-1]
                subprocess.run(['taskkill', '/PID', pid, '/F'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"  已释放端口 {port} (PID: {pid})")
    except Exception:
        pass  # 静默失败，不影响后续启动


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='FunctionMap - 代码函数调用关系可视化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py
  python main.py --port 8080
  python main.py --path ./my_project
        """,
    )

    parser.add_argument(
        '--host', default='127.0.0.1',
        help='监听地址（默认: 127.0.0.1）'
    )
    parser.add_argument(
        '--port', type=int, default=8000,
        help='监听端口（默认: 8000）'
    )
    parser.add_argument(
        '--path', default='',
        help='启动后自动填入的代码路径'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  FunctionMap - 代码函数调用关系可视化工具")
    print("=" * 60)
    print()
    print("  功能:")
    print("    1. 交互式函数调用拓扑图")
    print("    2. 点击函数查看参数传递关系")
    print("    3. 支持 Python / C++ / C / MATLAB")
    print()

    # 启动Web服务器
    from web.server import run_server

    # 如果有 --path 参数，通过环境变量传递给前端
    if args.path:
        abs_path = os.path.abspath(args.path)
        print(f"  目标路径: {abs_path}")
        os.environ['FUNCTIONMAP_DEFAULT_PATH'] = abs_path

    # 如果端口被占用，自动释放
    _free_port(args.port)

    print(f"  访问 http://{args.host}:{args.port} 开始使用")
    print()
    run_server(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
