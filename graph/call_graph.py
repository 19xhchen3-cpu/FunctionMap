"""图构建器 - 根据解析结果构建 networkx 有向图"""

import re
from collections import defaultdict

import networkx as nx

from models.function_node import FunctionNode
from models.call_edge import CallEdge


class CallGraph:
    """
    函数调用关系图构建器

    将解析器产出的 FunctionNode 和 CallEdge 数据
    转化为一个完整的 networkx.DiGraph，并附带以下功能：
    - 拓扑层级计算
    - 节点按文件/语言着色
    - 参数流信息查询
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self._node_map: dict[str, FunctionNode] = {}   # id -> FunctionNode
        self._edges_map: dict[str, list[CallEdge]] = defaultdict(list)  # caller_id -> edges
        self._reverse_edges_map: dict[str, list[CallEdge]] = defaultdict(list)  # callee_id -> edges

    def build(self, functions: list[FunctionNode], edges: list[CallEdge]) -> nx.DiGraph:
        """
        从解析结果构建完整的有向图

        参数:
            functions: 所有函数节点
            edges: 所有调用边

        返回:
            networkx.DiGraph 实例
        """
        self.graph.clear()
        self._node_map.clear()
        self._edges_map.clear()

        # 添加节点（去重：同ID的保留第一个，后续的丢弃）
        seen_ids: set[str] = set()
        for func in functions:
            if func.id in seen_ids:
                continue
            seen_ids.add(func.id)
            self._node_map[func.id] = func
            self.graph.add_node(
                func.id,
                # 节点可视化属性
                label=func.short_name,
                title=func.signature,           # 悬停提示
                file=func.file_path,
                language=func.language,
                params=func.params,
                class_name=func.class_name,
                line_start=func.line_start,
                line_end=func.line_end,
                # PyVis group（用于着色）
                group=func.language,
                # 节点大小（带参数多的稍大）
                size=min(30, 15 + len(func.params) * 2),
            )

        # 添加边（去重 + 过滤self-loop）
        seen_edges: set[tuple[str, str, int]] = set()
        for edge in edges:
            if edge.caller_id == edge.callee_id:
                continue  # 过滤self-loop（通常是正则解析的误匹配）
            edge_key = (edge.caller_id, edge.callee_id, edge.call_line)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            self._edges_map[edge.caller_id].append(edge)
            self._reverse_edges_map[edge.callee_id].append(edge)

            # 决定边样式
            dashes = not edge.is_resolved  # 未解析的边用虚线

            # 构建边标签（参数信息）
            edge_label = ', '.join(edge.args) if edge.args else ''

            self.graph.add_edge(
                edge.caller_id,
                edge.callee_id,
                # 边的可视化属性
                label=edge_label,
                title=f"行 {edge.call_line}: {edge.caller_id} → {edge.callee_id}",
                dashes=dashes,
                call_line=edge.call_line,
                args=edge.args,
                is_resolved=edge.is_resolved,
                callee_name=edge.callee_name,
                # 未解析的边颜色更淡
                color='rgba(200,200,200,0.5)' if not edge.is_resolved else None,
            )

        # 跨文件解析：尝试解析其他文件中定义的函数
        self._resolve_cross_file_edges()

        return self.graph

    def add_cross_language_edges(self) -> None:
        """
        后处理阶段：在 C++ 函数与 Qt UI widget 节点之间创建跨语言调用边。

        扫描 C++ 函数体中的 ui->widgetName 模式，将每个引用链接到对应的
        UI widget 伪函数节点，实现跨语言调用关系可视化。
        """
        # 收集所有 UI widget 节点
        ui_nodes = {
            func_id: func
            for func_id, func in self._node_map.items()
            if func.language == 'ui'
        }
        if not ui_nodes:
            return

        # 构建 widget_name -> FunctionNode 映射
        widget_map: dict[str, FunctionNode] = {}
        for func_id, func in ui_nodes.items():
            widget_map[func.name] = func

        # 在 C++ 源码中查找 ui->widgetName 的模式
        ui_ref_pattern = re.compile(r'ui\s*->\s*([a-zA-Z_]\w*)')

        # 遍历所有 C++ 函数节点
        for func_id, func in list(self._node_map.items()):
            if func.language not in ('cpp', 'c'):
                continue

            # 读取源文件，在函数范围内查找 ui-> 引用
            try:
                with open(func.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            except Exception:
                continue

            for lineno in range(max(0, func.line_start - 1), min(len(lines), func.line_end)):
                line = lines[lineno]
                for match in ui_ref_pattern.finditer(line):
                    widget_name = match.group(1)
                    if widget_name not in widget_map:
                        continue

                    widget_func = widget_map[widget_name]
                    widget_func_id = widget_func.id

                    # 防止自环和重复边
                    if widget_func_id == func_id:
                        continue
                    if self.graph.has_edge(func_id, widget_func_id):
                        continue

                    edge = CallEdge(
                        caller_id=func_id,
                        callee_id=widget_func_id,
                        call_line=lineno + 1,
                        args=[],
                        is_resolved=True,
                        callee_name=widget_name,
                    )
                    self._edges_map[func_id].append(edge)
                    self._reverse_edges_map[widget_func_id].append(edge)

                    self.graph.add_edge(
                        func_id, widget_func_id,
                        label='',
                        title=f"ui->{widget_name} at line {lineno + 1}",
                        dashes=False,
                        call_line=lineno + 1,
                        args=[],
                        is_resolved=True,
                        callee_name=widget_name,
                        # 绿色边表示跨语言引用
                        color='rgba(100,200,100,0.7)',
                    )

    def _resolve_cross_file_edges(self) -> None:
        """
        第二遍解析：遍历所有未解析的边，尝试在 _node_map 中跨文件匹配函数。

        仅当 _node_map 中恰好有一个函数名与 callee_name 匹配时才解析。
        如果有多个同名函数（来自不同文件），则跳过不解析。
        """
        # 收集待解析的边（先收集再修改，避免迭代时变更字典）
        candidates: list[tuple[str, CallEdge]] = []
        for caller_id, edge_list in self._edges_map.items():
            for edge in edge_list:
                if edge.is_resolved:
                    continue
                if not edge.callee_name:
                    continue
                candidates.append((edge.callee_id, edge))

        for old_callee_id, edge in candidates:
            callee_name = edge.callee_name

            # 在 _node_map 中查找匹配的函数
            matches = [
                func for func in self._node_map.values()
                if func.name == callee_name
            ]

            if len(matches) != 1:
                continue  # 0 个或多个匹配 → 跳过

            resolved_func = matches[0]
            new_callee_id = resolved_func.id

            # 防止解析后变成自环
            if new_callee_id == edge.caller_id:
                continue

            # 防止创建重复边
            if self.graph.has_edge(edge.caller_id, new_callee_id):
                existing = self.graph.get_edge_data(edge.caller_id, new_callee_id)
                if existing and existing.get('call_line') == edge.call_line:
                    continue

            # 从旧的反向索引中移除
            old_rev = self._reverse_edges_map.get(old_callee_id)
            if old_rev is not None and edge in old_rev:
                old_rev.remove(edge)

            # 更新 CallEdge
            edge.callee_id = new_callee_id
            edge.is_resolved = True

            # 添加到新的反向索引
            self._reverse_edges_map[new_callee_id].append(edge)

            # 删除旧 networkx 边
            # 注意：同一 caller 可能有多个同 callee_name 的未解析边（如多处调用 .add()），
            # 第一次删除后，后续同 (caller, old_callee_id) 的边已在图中被覆盖，需要跳过
            if self.graph.has_edge(edge.caller_id, old_callee_id):
                self.graph.remove_edge(edge.caller_id, old_callee_id)

            # 添加新边（实线，正常颜色）
            self.graph.add_edge(
                edge.caller_id,
                new_callee_id,
                label=', '.join(edge.args) if edge.args else '',
                title=f"行 {edge.call_line}: {edge.caller_id} → {new_callee_id}",
                dashes=False,
                call_line=edge.call_line,
                args=edge.args,
                is_resolved=True,
                callee_name=edge.callee_name,
                color=None,
            )

    def get_topological_layers(self) -> list[list[str]]:
        """
        计算拓扑层级（用于分层布局）

        如果图中有环（递归调用），会进行特殊处理
        """
        try:
            # 尝试拓扑排序
            layers = list(nx.topological_generations(self.graph))
            return [list(layer) for layer in layers]
        except nx.NetworkXUnfeasible:
            # 有环（递归/互调）时，使用启发式分层
            return self._layered_layout_with_cycles()

    def _layered_layout_with_cycles(self) -> list[list[str]]:
        """
        处理有环图的拓扑分层

        使用最长路径长度作为层级
        """
        # 用最长路径近似拓扑层级
        try:
            # 找到所有源节点（入度为0）
            sources = [n for n in self.graph.nodes() if self.graph.in_degree(n) == 0]
            if not sources:
                # 没有源节点（全是环），随机选一个作为起点
                sources = [list(self.graph.nodes())[0]]

            # 计算每个节点到最近源节点的最长距离
            dist = {}
            for s in sources:
                for n in nx.dfs_preorder_nodes(self.graph, s):
                    if n not in dist:
                        dist[n] = 0
                    for succ in self.graph.successors(n):
                        new_dist = dist[n] + 1
                        if succ not in dist or new_dist > dist[succ]:
                            dist[succ] = new_dist

            # 按距离分组
            max_dist = max(dist.values()) if dist else 0
            layers: list[list[str]] = [[] for _ in range(max_dist + 1)]
            for node, d in dist.items():
                layers[d].append(node)

            return layers
        except Exception:
            # 兜底：所有节点放在一层
            return [list(self.graph.nodes())]

    def get_callers(self, func_id: str) -> list[CallEdge]:
        """获取所有调用了给定函数的边（使用反向索引，O(1)）"""
        return self._reverse_edges_map.get(func_id, [])

    def get_callees(self, func_id: str) -> list[CallEdge]:
        """获取给定函数调用的所有边"""
        return self._edges_map.get(func_id, [])

    def get_function_detail(self, func_id: str) -> dict | None:
        """获取函数的详细信息"""
        func = self._node_map.get(func_id)
        if not func:
            return None

        callers = self.get_callers(func_id)
        callees = self.get_callees(func_id)

        return {
            'id': func.id,
            'name': func.name,
            'short_name': func.short_name,
            'signature': func.signature,
            'file_path': func.file_path,
            'language': func.language,
            'params': func.params,
            'return_type': func.return_type,
            'class_name': func.class_name,
            'line_start': func.line_start,
            'line_end': func.line_end,
            'callers': [
                {
                    'id': e.caller_id,
                    'args': e.args,
                    'line': e.call_line,
                    'is_resolved': e.is_resolved,
                    'callee_name': e.callee_name,
                }
                for e in callers
            ],
            'callees': [
                {
                    'id': e.callee_id,
                    'args': e.args,
                    'line': e.call_line,
                    'is_resolved': e.is_resolved,
                    'callee_name': e.callee_name,
                }
                for e in callees
            ],
        }

    def get_functions_list(self) -> list[dict]:
        """获取所有函数列表，按文件分组（用于左侧sidebar）"""
        from collections import defaultdict
        files_map: dict[str, list[dict]] = defaultdict(list)

        for func_id, func in self._node_map.items():
            files_map[func.file_path].append({
                'id': func.id,
                'name': func.name,
                'short_name': func.short_name,
                'signature': func.signature,
                'params': func.params,
                'class_name': func.class_name,
                'language': func.language,
                'line_start': func.line_start,
            })

        # 每个文件内的函数按行号排序
        for file_path in files_map:
            files_map[file_path].sort(key=lambda f: f['line_start'])

        # 文件按路径排序
        sorted_files = sorted(files_map.items(), key=lambda x: x[0])

        return [
            {'file_path': fp, 'functions': funcs}
            for fp, funcs in sorted_files
        ]

    def extract_subgraph(self, center_id: str, depth: int = 3,
                          max_nodes: int = 300) -> dict | None:
        """
        提取以 center_id 为中心，depth 层范围内的子图

        BFS双向扩展: 向上找callers, 向下找callees
        max_nodes: 子图节点数上限，超过此限制时截断（防止界面卡死）

        返回的每个节点包含:
        - level: 层级布局用的层级值（0=最左, 2*depth=最右）
        - is_external: 是否为外部函数
        """
        if center_id not in self._node_map:
            return None

        truncated = False

        # BFS向上（找callers）
        up_nodes: dict[str, int] = {center_id: 0}
        down_nodes: dict[str, int] = {center_id: 0}
        queue = [(center_id, 0)]
        while queue:
            node_id, d = queue.pop(0)
            if d >= depth:
                continue
            for edge in self.get_callers(node_id):
                caller = edge.caller_id
                if caller not in up_nodes:
                    # 检查节点数是否超过上限（防止界面卡死）
                    if len(up_nodes) + len(down_nodes) - 1 >= max_nodes:
                        truncated = True
                        continue
                    up_nodes[caller] = d + 1
                    queue.append((caller, d + 1))

        # BFS向下（找callees，包括外部函数）
        queue = [(center_id, 0)]
        while queue:
            node_id, d = queue.pop(0)
            if d >= depth:
                continue
            for edge in self.get_callees(node_id):
                callee = edge.callee_id
                if callee not in down_nodes:
                    # 检查节点数是否超过上限
                    if len(up_nodes) + len(down_nodes) - 1 >= max_nodes:
                        truncated = True
                        continue
                    down_nodes[callee] = d + 1
                    queue.append((callee, d + 1))

        # 去重合并
        all_node_ids = set(up_nodes.keys()) | set(down_nodes.keys())

        # 为外部函数ID收集名称映射
        external_names: dict[str, str] = {}
        for caller_id in all_node_ids:
            for edge in self._edges_map.get(caller_id, []):
                if not edge.is_resolved and edge.callee_id not in self._node_map:
                    external_names[edge.callee_id] = edge.callee_name or edge.callee_id

        # 缓存反向边中未解决的外部调用者
        for nid in list(all_node_ids):
            for edge in self._reverse_edges_map.get(nid, []):
                if not edge.is_resolved and edge.caller_id not in self._node_map:
                    all_node_ids.add(edge.caller_id)
                    external_names[edge.caller_id] = edge.callee_name or edge.caller_id
                    # 这个外部调用者在层级上属于caller侧
                    if edge.caller_id not in up_nodes:
                        up_nodes[edge.caller_id] = 1

        # 构建节点列表（带level层级信息和外部节点）
        nodes_out = []
        for nid in all_node_ids:
            func = self._node_map.get(nid)
            d = min(up_nodes.get(nid, 999), down_nodes.get(nid, 999))

            # 确定层级位置（用于从左到右布局）
            if nid == center_id:
                level = depth
            elif nid in up_nodes and nid not in down_nodes:
                level = depth - up_nodes[nid]  # callers在左侧
            elif nid in down_nodes and nid not in up_nodes:
                level = depth + down_nodes[nid]  # callees在右侧
            else:
                # 既是caller又是callee（环），取距离中心近的一侧
                up_d = up_nodes.get(nid, 999)
                down_d = down_nodes.get(nid, 999)
                if up_d <= down_d:
                    level = depth - up_d
                else:
                    level = depth + down_d

            if func:
                nodes_out.append({
                    'id': func.id,
                    'label': func.short_name,
                    'title': func.signature,
                    'file': func.file_path,
                    'language': func.language,
                    'group': func.language,
                    'params': func.params,
                    'class_name': func.class_name,
                    'size': min(30, 15 + len(func.params) * 2),
                    'depth': d,
                    'level': max(0, min(level, depth * 2)),
                    'is_external': False,
                })
            else:
                # 外部函数伪节点
                ext_name = external_names.get(nid, nid)
                nodes_out.append({
                    'id': nid,
                    'label': ext_name.split('::')[-1] if '::' in ext_name else ext_name,
                    'title': f'[外部函数] {ext_name}',
                    'file': '',
                    'language': 'external',
                    'group': 'external',
                    'params': [],
                    'class_name': '',
                    'size': 15,
                    'depth': d,
                    'level': min(level, depth * 2),
                    'is_external': True,
                })

        # 压缩层级：消除空白列间隙
        self._compact_levels(nodes_out, center_id)

        # 构建边列表（包括连接到外部节点的边）
        edges_out = []
        seen_edge_keys: set[tuple[str, str, int]] = set()
        for caller_id in all_node_ids:
            for edge in self._edges_map.get(caller_id, []):
                if edge.callee_id not in all_node_ids:
                    continue
                ekey = (edge.caller_id, edge.callee_id, edge.call_line)
                if ekey in seen_edge_keys:
                    continue
                seen_edge_keys.add(ekey)
                edges_out.append({
                    'from': edge.caller_id,
                    'to': edge.callee_id,
                    'label': ', '.join(edge.args) if edge.args else '',
                    'title': f"行 {edge.call_line}: {edge.caller_id} → {edge.callee_id}",
                    'dashes': not edge.is_resolved,
                    'args': edge.args,
                    'is_resolved': edge.is_resolved,
                    'callee_name': edge.callee_name,
                })

        return {
            'nodes': nodes_out,
            'edges': edges_out,
            'center': center_id,
            'depth': depth,
            'truncated': truncated,
        }

    @staticmethod
    def _compact_levels(nodes_out: list[dict], center_id: str) -> None:
        """
        压缩层级值，消除空白间隙。

        extract_subgraph() 产生的 level 在 [0, 2*depth] 范围内。
        当某些层级没有节点时，如 [2, 3, 4]，vis-network 仍会为 0, 1, 5, 6
        保留等宽间距，导致大量空白。

        此方法将使用的 level 值重新映射为连续整数，如 [2, 3, 4] → [0, 1, 2]。
        """
        used_levels = sorted({n['level'] for n in nodes_out})
        if len(used_levels) <= 1:
            return
        # 重新映射为从 0 开始的连续整数，消除偏移和间隙
        level_map: dict[int, int] = {
            old: new for new, old in enumerate(used_levels)
        }
        for node in nodes_out:
            node['level'] = level_map[node['level']]

    def trace_parameter(self, func_id: str, param_name: str) -> dict | None:
        """
        追踪某个参数在调用关系中的流向

        匹配策略:
        - 按位置匹配 caller 实参 → callee 形参
        - 也支持关键字参数匹配 (如 param_name=value)
        """
        func_node = self._node_map.get(func_id)
        if not func_node:
            return None

        # 找到参数索引
        param_idx = None
        for i, p in enumerate(func_node.params):
            if p == param_name:
                param_idx = i
                break

        if param_idx is None:
            return None

        incoming: list[dict] = []
        outgoing: list[dict] = []

        # --- 传入: 哪些caller传了实参到这个参数 ---
        for edge in self.get_callers(func_id):
            # 按位置匹配
            if param_idx < len(edge.args):
                incoming.append({
                    'from': edge.caller_id,
                    'to': func_id,
                    'caller_arg': edge.args[param_idx],
                    'param_index': param_idx,
                    'call_line': edge.call_line,
                    'is_resolved': edge.is_resolved,
                })
            # 关键字匹配: "param_name=value" 格式
            for arg in edge.args:
                if '=' in arg:
                    kw, val = arg.split('=', 1)
                    if kw.strip() == param_name:
                        incoming.append({
                            'from': edge.caller_id,
                            'to': func_id,
                            'caller_arg': val.strip(),
                            'param_index': -1,
                            'call_line': edge.call_line,
                            'is_resolved': edge.is_resolved,
                        })

        # --- 传出: 该参数是否被转发给callee ---
        for edge in self.get_callees(func_id):
            callee_node = self._node_map.get(edge.callee_id)
            for i, arg in enumerate(edge.args):
                if arg == param_name:
                    callee_param = '?'
                    if callee_node and i < len(callee_node.params):
                        callee_param = callee_node.params[i]
                    outgoing.append({
                        'from': func_id,
                        'to': edge.callee_id,
                        'forwarded_as': arg,
                        'callee_param': callee_param,
                        'param_index': i,
                        'call_line': edge.call_line,
                        'is_resolved': edge.is_resolved,
                    })

        return {
            'func_id': func_id,
            'param': param_name,
            'incoming': incoming,
            'outgoing': outgoing,
        }

    def trace_path(self, src_id: str, dst_id: str,
                    max_paths: int = 5, cutoff: int = 10) -> dict | None:
        """
        查找从 src_id 到 dst_id 的所有调用路径。

        使用 networkx 的路径查找算法：
        1. 先找最短路径（最直接的调用链）
        2. 再在 cutoff 跳范围内找其他路径（不重复）

        参数:
            src_id: 起始函数 ID
            dst_id: 目标函数 ID
            max_paths: 最多返回路径数（防止超大图路径爆炸）
            cutoff: 路径最大长度（跳数），默认 10

        返回:
            {
                'src_id': '...',
                'dst_id': '...',
                'src_name': 'funcA',
                'dst_name': 'funcB',
                'paths': [
                    {
                        'length': 3,
                        'steps': [
                            {'from': 'A', 'to': 'B', 'call_line': 42, 'args': ['x']},
                            {'from': 'B', 'to': 'C', 'call_line': 55, 'args': ['y']},
                        ],
                        'nodes_in_path': ['A', 'B', 'C'],
                    }
                ],
                'total_paths_found': 1,
            }
            如果任一函数不存在，返回 None
        """
        if src_id not in self._node_map or dst_id not in self._node_map:
            return None

        if src_id == dst_id:
            return {
                'src_id': src_id,
                'dst_id': dst_id,
                'src_name': self._node_map[src_id].short_name,
                'dst_name': self._node_map[dst_id].short_name,
                'paths': [],
                'total_paths_found': 0,
                'message': '起始函数和目标函数相同',
            }

        result_paths = []
        seen_path_sigs: set[str] = set()  # 去重

        # 1. 查找最短路径
        try:
            sp = nx.shortest_path(self.graph, src_id, dst_id)
            sig = '->'.join(sp)
            if sig not in seen_path_sigs:
                seen_path_sigs.add(sig)
                result_paths.append(self._path_to_steps(sp))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        # 2. 在 cutoff 范围内查找所有简单路径，直到达到 max_paths
        if len(result_paths) < max_paths:
            try:
                for path in nx.all_simple_paths(self.graph, src_id, dst_id, cutoff=cutoff):
                    if len(result_paths) >= max_paths:
                        break
                    sig = '->'.join(path)
                    if sig not in seen_path_sigs:
                        seen_path_sigs.add(sig)
                        result_paths.append(self._path_to_steps(path))
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass

        src_name = self._node_map[src_id].short_name if src_id in self._node_map else src_id
        dst_name = self._node_map[dst_id].short_name if dst_id in self._node_map else dst_id

        return {
            'src_id': src_id,
            'dst_id': dst_id,
            'src_name': src_name,
            'dst_name': dst_name,
            'paths': result_paths,
            'total_paths_found': len(result_paths),
        }

    def _path_to_steps(self, path: list[str]) -> dict:
        """
        将 networkx 的路径（节点ID列表）转为步骤列表

        每步包含:
        - from: 调用者ID
        - to: 被调用者ID
        - call_line: 调用行号
        - args: 实参列表
        """
        steps = []
        for i in range(len(path) - 1):
            frm = path[i]
            to = path[i + 1]
            edge_data = self.graph.get_edge_data(frm, to) or {}
            frm_name = self._node_map[frm].short_name if frm in self._node_map else frm.split('::')[-1]
            to_name = self._node_map[to].short_name if to in self._node_map else to.split('::')[-1]
            steps.append({
                'from': frm,
                'to': to,
                'from_name': frm_name,
                'to_name': to_name,
                'call_line': edge_data.get('call_line', 0),
                'args': edge_data.get('args', []),
            })

        return {
            'length': len(steps),
            'steps': steps,
            'nodes_in_path': path,
        }

    def get_unresolved_calls(self) -> list[dict]:
        """获取所有未解析的外部调用"""
        unresolved = []
        for u, v, data in self.graph.edges(data=True):
            if not data.get('is_resolved', True):
                unresolved.append({
                    'from': u,
                    'to': v,
                    'name': data.get('callee_name', ''),
                    'line': data.get('call_line', 0),
                })
        return unresolved

    def to_json(self) -> dict:
        """将图序列化为JSON（用于前端传输）"""
        # 标准化节点
        nodes = []
        for nid, data in self.graph.nodes(data=True):
            nodes.append({
                'id': nid,
                'label': data.get('label', nid),
                'title': data.get('title', ''),
                'file': data.get('file', ''),
                'language': data.get('language', ''),
                'group': data.get('group', ''),
                'params': data.get('params', []),
                'size': data.get('size', 20),
            })

        # 标准化边
        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append({
                'from': u,
                'to': v,
                'label': data.get('label', ''),
                'title': data.get('title', ''),
                'dashes': data.get('dashes', False),
                'args': data.get('args', []),
                'is_resolved': data.get('is_resolved', True),
                'callee_name': data.get('callee_name', ''),
            })

        return {
            'nodes': nodes,
            'edges': edges,
        }

    @property
    def node_count(self) -> int:
        """图节点数"""
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """图边数"""
        return self.graph.number_of_edges()
