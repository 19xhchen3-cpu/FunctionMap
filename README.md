# FunctionMap - 代码函数调用关系可视化工具

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![vis.js](https://img.shields.io/badge/vis--network-9.1.6-orange)

一个轻量级的**代码函数调用关系可视化工具**。扫描指定目录下的源代码文件，自动解析函数定义和调用关系，生成交互式调用关系图，帮助开发者快速理解代码结构和数据流向。

## 功能特性

- 🔍 **自动扫描** — 递归扫描文件夹，自动识别 Python、C/C++、MATLAB 源文件
- 🕸️ **交互式调用图** — 基于 vis-network 的层级布局，左侧调用者 → 中心函数 → 右侧被调用者
- 📋 **函数列表导航** — 左侧边栏按文件分组显示所有函数，支持搜索过滤
- 🔬 **局部子图** — 点击函数仅显示其周围 ±3 层的调用关系，避免大图卡死
- 🔗 **参数流追踪** — 点击参数名，图中高亮显示参数的传入来源和传出去向（红进绿出）
- 🖱️ **双击跳转** — 双击任意函数节点快速跳转到该函数的子图
- 🌐 **外部函数标识** — 未解析的外部函数以灰色节点和虚线边区分显示
- ⚡ **大图保护** — 子图节点超过 300 个时自动截断并提示，防止界面卡死

## 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装

```bash
# 克隆仓库
git clone https://github.com/19xhchen3-cpu/FunctionMap.git
cd FunctionMap

# 安装依赖
pip install -r requirements.txt
```

### 使用

```bash
# 启动服务器（默认 http://127.0.0.1:8000）
python main.py

# 指定端口
python main.py --port 8080

# 指定主机
python main.py --host 0.0.0.0

# 启动时自动扫描指定目录
python main.py --path /path/to/code
```

启动后用浏览器打开 `http://127.0.0.1:8000`，输入代码文件夹路径点击"开始扫描"即可。

### 快速体验

项目自带测试项目，可直接扫描测试：

```bash
python main.py --path test_project/
# 打开 http://127.0.0.1:8000
```

## 用户交互流程

```
输入文件夹路径 → 开始扫描 → 左侧显示函数列表
                              ↓
                     点击函数 → 渲染局部调用子图
                              ↓
                     点击参数 → 红/绿着色显示参数流向
                              ↓
                   双击函数节点 → 跳转到该函数的子图
```

## 支持的编程语言

| 语言 | 解析方式 | 文件扩展名 |
|------|----------|-----------|
| Python | 内置 `ast` 模块（零依赖） | `.py` |
| C++ | tree-sitter-cpp（首选）/ 正则（兜底） | `.cpp` `.hpp` `.h++` |
| C | tree-sitter-c（首选）/ 正则（兜底） | `.c` `.h` |
| MATLAB | 正则匹配 | `.m` |

> **关于 C/C++ 解析**：tree-sitter 提供精确的 AST 解析，需要额外安装 `pip install tree-sitter tree-sitter-cpp tree-sitter-c`。未安装时自动降级为正则匹配（零依赖可用，精度略低）。

## 技术架构

```
scanner/file_scanner.py     文件扫描：递归遍历目录，按扩展名分组
        ↓
parsers/*_parser.py         语言解析：提取函数定义和调用关系
        ↓
graph/call_graph.py         图构建：构建 networkx DiGraph，子图提取，参数流追踪
        ↓
web/server.py               FastAPI 后端：REST API 服务
        ↓
web/static/app.js           前端交互：vis-network 渲染 + 子图/参数流操作
```

### 数据模型

- **FunctionNode**: 函数节点（id、名称、文件路径、行号范围、参数列表、返回值类型、所属类名）
- **CallEdge**: 调用边（调用者、被调用者、调用行号、实参、是否已解析）

### API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/scan` | 扫描文件夹 → 解析 → 建图 |
| GET | `/api/graph/{id}/functions` | 获取函数列表（侧边栏数据） |
| GET | `/api/graph/{id}/subgraph?func_id=X&depth=3` | 获取以某函数为中心的子图 |
| GET | `/api/graph/{id}/param-flow?func_id=X&param=Y` | 追踪参数传递路径 |
| GET | `/api/function/{id}?func_id=X` | 获取函数详情（调用者/被调用者） |
| GET | `/api/graph/{id}/statistics` | 获取图统计信息（节点/边数量） |

## 开发

### 项目结构

```
FunctionMap/
├── main.py                     # 入口：启动 Web 服务器
├── scanner/
│   └── file_scanner.py         # 文件递归扫描器
├── parsers/
│   ├── base_parser.py          # 解析器抽象基类
│   ├── python_parser.py        # Python 解析器
│   ├── cpp_parser.py           # C/C++ 解析器
│   └── matlab_parser.py        # MATLAB 解析器
├── models/
│   ├── function_node.py        # 函数节点数据模型
│   └── call_edge.py            # 调用边数据模型
├── graph/
│   └── call_graph.py           # 调用关系图构建与查询
├── web/
│   ├── server.py               # FastAPI 服务器
│   ├── static/
│   │   ├── app.js              # 前端交互逻辑
│   │   └── style.css           # 页面样式
│   └── templates/
│       └── index.html          # 主页面
└── test_project/               # 测试项目（含多语言示例代码）
```

### 依赖

- **核心**: fastapi, uvicorn, networkx, jinja2, python-multipart
- **前端**: vis-network 9.1.6（CDN 加载）
- **可选**: tree-sitter + tree-sitter-cpp + tree-sitter-c（C/C++ 精确解析）

## 常见问题

**Q: 扫描后图中函数太多，界面卡顿怎么办？**
A: 点击侧边栏中的具体函数，仅显示该函数周围的局部子图，避免一次性渲染所有节点。系统也会自动限制子图最大 300 个节点。

**Q: 为什么有些函数显示为灰色节点和虚线？**
A: 灰色节点表示外部函数（如标准库、第三方库函数），这些函数不在扫描目录内，无法进一步展开。

**Q: 跨文件函数调用能否正确解析？**
A: 可以。系统在构建图时会尝试将未解析的调用与所有已扫描文件中的函数进行匹配，同一项目内跨文件调用会自动解析。

## License

MIT
