"""FastAPI Web服务器 - 提供代码分析API和可视化界面"""

import asyncio
import os
import sys
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
import uvicorn

from scanner.file_scanner import scan_files_flat
from graph.call_graph import CallGraph


# 存储不同扫描会话的图
_graph_store: dict[str, CallGraph] = {}

# 存储扫描进度
_scan_progress: dict[str, dict] = {}

app = FastAPI(
    title="FunctionMap - 代码函数调用关系可视化工具",
    version="1.0.0",
    description="扫描代码文件夹，生成交互式函数调用关系拓扑图",
)

# 获取资源基础路径（支持 PyInstaller 打包后的 sys._MEIPASS）
if getattr(sys, 'frozen', False):
    # PyInstaller: 所有文件解压到 sys._MEIPASS
    BASE_DIR = sys._MEIPASS
else:
    # 开发模式: 项目根目录（web/ 的父目录）
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMPLATE_PATH = os.path.join(BASE_DIR, "web", "templates", "index.html")
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")


@app.get("/static/{path:path}")
async def serve_static(path: str):
    """提供静态文件服务"""
    file_path = os.path.join(STATIC_DIR, path)
    # 防止路径穿越攻击
    if os.path.abspath(file_path).startswith(os.path.abspath(STATIC_DIR)):
        if os.path.isfile(file_path):
            return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面 - 直接返回静态HTML"""
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>FunctionMap</h1><p>index.html not found</p>")


class ScanRequest(BaseModel):
    """扫描请求"""
    folder_path: str


@app.post("/api/scan")
async def scan_folder(req: ScanRequest) -> JSONResponse:
    """
    扫描文件夹，解析代码，构建调用关系图

    步骤:
    1. 扫描文件夹收集所有源文件
    2. 为每个文件选择合适的解析器
    3. 解析所有文件提取函数和调用
    4. 构建有向图
    5. 返回图ID和相关统计
    """
    folder_path = os.path.normpath(req.folder_path)

    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"路径不存在或不是目录: {folder_path}")

    # 生成唯一图ID
    graph_id = str(uuid.uuid4())[:8]

    # 扫描文件
    print(f"开始扫描: {folder_path}")
    files = scan_files_flat(folder_path)
    if not files:
        raise HTTPException(status_code=400,
                            detail=f"在 {folder_path} 中未找到支持的代码文件 "
                                   f"(.py, .cpp, .c, .h, .hpp, .m)")

    print(f"发现 {len(files)} 个源文件")

    # 按语言分组
    by_lang: dict[str, list[str]] = {}
    for file_path, lang in files:
        by_lang.setdefault(lang, []).append(file_path)

    file_summary = ', '.join(f"{lang}: {len(paths)}个" for lang, paths in by_lang.items())
    print(f"  文件分布: {file_summary}")

    # 懒导入所有解析器
    from parsers.python_parser import PythonParser
    from parsers.cpp_parser import CppParser
    from parsers.matlab_parser import MatlabParser

    parser_map = {
        'python': PythonParser(),
        'cpp': CppParser(),
        'c': CppParser(),      # C和C++共用解析器
        'matlab': MatlabParser(),
    }

    # 解析所有文件
    all_functions = []
    all_edges = []

    for lang, lang_files in by_lang.items():
        parser = parser_map.get(lang)
        if parser is None:
            print(f"  跳过不支持的语言: {lang}")
            continue

        print(f"  解析 {lang} 文件 ({len(lang_files)}个)...")
        for file_path in lang_files:
            funcs, edges = parser.parse_file(file_path)
            all_functions.extend(funcs)
            all_edges.extend(edges)

    print(f"  共找到 {len(all_functions)} 个函数, {len(all_edges)} 条调用关系")

    # 构建图
    call_graph = CallGraph()
    call_graph.build(all_functions, all_edges)

    # 存储
    _graph_store[graph_id] = call_graph

    unresolved = call_graph.get_unresolved_calls()

    return JSONResponse({
        'graph_id': graph_id,
        'message': f"扫描完成: 发现 {len(all_functions)} 个函数, "
                   f"{len(all_edges)} 条调用关系, "
                   f"{len(unresolved)} 个外部调用",
        'node_count': call_graph.node_count,
        'edge_count': call_graph.edge_count,
        'unresolved_count': len(unresolved),
        'file_summary': file_summary,
        'language_stats': {lang: len(paths) for lang, paths in by_lang.items()},
    })


@app.get("/api/graph/{graph_id}")
async def get_graph(graph_id: str) -> JSONResponse:
    """获取指定扫描的完整图数据"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")

    return JSONResponse(call_graph.to_json())


@app.get("/api/graph/{graph_id}/functions")
async def get_graph_functions(graph_id: str) -> JSONResponse:
    """获取所有函数列表（按文件分组，用于左侧sidebar）"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")
    return JSONResponse(call_graph.get_functions_list())


@app.get("/api/graph/{graph_id}/subgraph")
async def get_subgraph(graph_id: str, func_id: str, depth: int = 3) -> JSONResponse:
    """获取以某函数为中心的局部子图（depth层范围内）"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")
    result = call_graph.extract_subgraph(func_id, depth)
    if result is None:
        raise HTTPException(status_code=404, detail=f"函数不存在: {func_id}")
    return JSONResponse(result)


@app.get("/api/graph/{graph_id}/param-flow")
async def get_param_flow(graph_id: str, func_id: str, param: str) -> JSONResponse:
    """追踪某个参数的流向"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")
    result = call_graph.trace_parameter(func_id, param)
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"函数或参数不存在: {func_id} / {param}")
    return JSONResponse(result)


@app.get("/api/graph/{graph_id}/trace-path")
async def get_trace_path(graph_id: str, from_id: str, to_id: str,
                          max_paths: int = 5) -> JSONResponse:
    """查找两个函数之间的调用路径"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")
    result = call_graph.trace_path(from_id, to_id, max_paths)
    if result is None:
        raise HTTPException(status_code=404,
                            detail="一个或两个函数不存在，请检查函数ID")
    return JSONResponse(result)


@app.get("/api/function/{graph_id}")
async def get_function_detail(graph_id: str, func_id: str) -> JSONResponse:
    """获取函数详情（使用查询参数传递func_id，避免路径编码问题）"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")

    detail = call_graph.get_function_detail(func_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"函数不存在: {func_id}")

    return JSONResponse(detail)


@app.get("/api/graph/{graph_id}/statistics")
async def get_graph_statistics(graph_id: str) -> JSONResponse:
    """获取图统计信息"""
    call_graph = _graph_store.get(graph_id)
    if call_graph is None:
        raise HTTPException(status_code=404, detail=f"图不存在: {graph_id}")

    return JSONResponse({
        'node_count': call_graph.node_count,
        'edge_count': call_graph.edge_count,
        'has_cycles': call_graph.get_topological_layers() is not None,
    })


@app.get("/api/browse-folder")
async def browse_folder():
    """打开系统原生文件夹选择对话框"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return JSONResponse({"path": "", "error": "tkinter not available"})

    loop = asyncio.get_event_loop()

    def _pick():
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory()
        root.destroy()
        return folder

    folder_path = await loop.run_in_executor(None, _pick)
    return JSONResponse({"path": folder_path or ""})


def run_server(host: str = '127.0.0.1', port: int = 8000):
    """启动服务器"""
    print(f"  FunctionMap 服务启动于 http://{host}:{port}")
    print(f"  打开浏览器访问 http://{host}:{port} 使用可视化工具")
    uvicorn.run(app, host=host, port=port, log_level='info')
