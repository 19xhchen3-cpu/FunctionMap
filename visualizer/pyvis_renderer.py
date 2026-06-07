"""PyVis可视化渲染器 - 将networkx图转为交互式HTML"""

import os
import tempfile

import networkx as nx
from pyvis.network import Network


class PyVisRenderer:
    """
    使用PyVis将函数调用关系图渲染为交互式HTML

    PyVis底层使用vis.js，支持：
    - 交互式拖拽、缩放
    - 物理引擎自动布局
    - 节点点击事件（可自定义）
    - 颜色分组
    """

    # 语言颜色映射
    LANGUAGE_COLORS = {
        'python': '#3572A5',
        'cpp': '#F34B7D',
        'c': '#555555',
        'matlab': '#E16737',
        'ui': '#41CD52',
    }

    # 未解析调用（外部函数）的颜色
    UNRESOLVED_NODE_COLOR = '#AAAAAA'

    def __init__(self, height: str = '700px', width: str = '100%',
                 bgcolor: str = '#ffffff', font_color: str = '#333333'):
        self.height = height
        self.width = width
        self.bgcolor = bgcolor
        self.font_color = font_color

    def render(self, graph: nx.DiGraph, output_path: str | None = None,
               notebook: bool = False) -> str:
        """
        将 networkx 有向图渲染为交互式HTML

        参数:
            graph: networkx 有向图
            output_path: 输出HTML路径（None则保存到临时文件）

        返回:
            HTML文件路径
        """
        # 创建 PyVis Network
        net = Network(
            height=self.height,
            width=self.width,
            bgcolor=self.bgcolor,
            font_color=self.font_color,
            directed=True,               # 有向图 - 箭头表示调用方向
            notebook=notebook,
        )

        # 配置物理引擎（用于自动布局）
        net.set_options("""
        {
          "physics": {
            "enabled": true,
            "stabilization": {
              "iterations": 100,
              "updateInterval": 25
            },
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
              "gravitationalConstant": -40,
              "centralGravity": 0.005,
              "springLength": 150,
              "springConstant": 0.08,
              "damping": 0.4
            }
          },
          "edges": {
            "smooth": {
              "type": "continuous",
              "roundness": 0.5
            },
            "arrows": {
              "to": {
                "enabled": true,
                "scaleFactor": 0.8
              }
            },
            "font": {
              "size": 10,
              "strokeWidth": 2,
              "align": "middle"
            }
          },
          "nodes": {
            "font": {
              "size": 14,
              "face": "Arial"
            },
            "borderWidth": 2,
            "shadow": {
              "enabled": true,
              "size": 4
            }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 200,
            "navigationButtons": true,
            "keyboard": true
          }
        }
        """)

        # 添加节点
        for nid, data in graph.nodes(data=True):
            lang = data.get('group', '') or data.get('language', '')
            color = self.LANGUAGE_COLORS.get(lang, '#97C2FC')

            title = data.get('title', '')
            if not title:
                title = nid

            net.add_node(
                nid,
                label=data.get('label', nid),
                title=title,
                color=color,
                size=data.get('size', 20),
                group=data.get('group', ''),
                # 额外数据（通过title传递，供前端的click判断）
                file=data.get('file', ''),
                language=lang,
                params=','.join(data.get('params', [])),
            )

        # 添加边
        for u, v, data in graph.edges(data=True):
            dashes = data.get('dashes', False)
            label = data.get('label', '')
            title = data.get('title', '')

            # 未解析的调用边用虚线 + 灰色
            edge_color = 'rgba(200,200,200,0.5)' if dashes else 'rgba(100,100,100,0.6)'

            net.add_edge(
                u, v,
                title=title or label,
                label=label,
                dashes=dashes,
                color=edge_color,
                width=1.5 if not dashes else 1,
                arrowStrikethrough=True,
            )

        # 生成HTML
        if output_path:
            net.save_graph(output_path)
        else:
            # 保存到临时文件
            fd, output_path = tempfile.mkstemp(suffix='.html', prefix='callgraph_')
            os.close(fd)
            net.save_graph(output_path)

        return output_path

    def render_to_html_string(self, graph: nx.DiGraph) -> str:
        """
        将图渲染为HTML字符串（不写文件）

        用于Web服务器的内联展示
        """
        # 先保存到临时文件，再读回来
        # 这是因为pyvis.save_graph()只能保存到文件
        tmp_path = self.render(graph)
        try:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                html = f.read()
            return html
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
