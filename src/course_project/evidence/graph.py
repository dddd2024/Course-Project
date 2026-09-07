import time
from typing import Dict, List, Any, Optional
import networkx as nx


class EvidenceGraph:
    """
    证据注册和依赖/溯源图管理
    Track C核心组件：记录所有证据及其来源和依赖关系
    """

    def __init__(self):
        # 证据存储：evidence_id -> evidence_data
        self.evidences: Dict[str, Dict[str, Any]] = {}

        # 依赖关系图：使用networkx构建有向图
        self.dependency_graph = nx.DiGraph()

        # 假设决策结果
        self.decisions: Dict[str, Dict[str, Any]] = {}

        # 证据来源权重配置
        self.source_weights = {
            'track_d_analysis': 0.8,  # 来自轨道D的基础分析
            'llm_generation': 0.7,  # LLM生成的假设
            'verifier': 0.9,  # 可执行验证器
            'manual_annotation': 0.95  # 人工标注
        }

    def register_evidence(self, evidence_id: str, evidence_data: Dict[str, Any],
                          source: str, dependencies: Optional[List[str]] = None) -> bool:
        """
        注册新证据到图中

        参数:
            evidence_id: 证据唯一标识符
            evidence_data: 证据数据内容
            source: 证据来源（track_d_analysis, llm_generation, verifier等）
            dependencies: 该证据依赖的其他证据ID列表

        返回:
            bool: 注册是否成功
        """
        if evidence_id in self.evidences:
            return False

        # 存储证据数据
        self.evidences[evidence_id] = {
            'data': evidence_data,
            'source': source,
            'timestamp': time.time(),
            'dependencies': dependencies or [],
            'weight': self.source_weights.get(source, 0.5)
        }

        # 添加到依赖图
        self.dependency_graph.add_node(evidence_id, **self.evidences[evidence_id])

        # 建立依赖边
        for dep_id in (dependencies or []):
            if dep_id in self.evidences:
                self.dependency_graph.add_edge(dep_id, evidence_id)

        return True

    def get_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定证据的详细信息
        """
        return self.evidences.get(evidence_id)

    def trace_provenance(self, evidence_id: str) -> List[Dict[str, Any]]:
        """
        追溯证据的来源和依赖链

        参数:
            evidence_id: 要追溯的证据ID

        返回:
            依赖链路列表，从最底层依赖到当前证据
        """
        provenance_chain = []

        if evidence_id not in self.evidences:
            return provenance_chain

        # 使用BFS遍历依赖关系
        visited = set()
        queue = [(evidence_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited:
                continue

            visited.add(current_id)
            evidence = self.evidences[current_id]

            provenance_chain.append({
                'evidence_id': current_id,
                'source': evidence['source'],
                'timestamp': evidence['timestamp'],
                'dependencies': evidence['dependencies'],
                'depth': depth
            })

            # 添加依赖项到队列
            for dep_id in evidence['dependencies']:
                if dep_id in self.evidences and dep_id not in visited:
                    queue.append((dep_id, depth + 1))

        # 按深度排序，从底层到顶层
        provenance_chain.sort(key=lambda x: x['depth'])
        return provenance_chain

    def get_related_evidences(self, hypothesis_id: str) -> List[str]:
        """
        获取与特定假设相关的所有证据ID
        """
        related = []
        for evidence_id, evidence in self.evidences.items():
            if evidence['data'].get('related_hypothesis') == hypothesis_id:
                related.append(evidence_id)
        return related

    def visualize_dependency_graph(self, output_path: str = None):
        """
        可视化依赖关系图（用于调试和分析）
        """
        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(self.dependency_graph)

        # 按来源类型着色
        color_map = {
            'track_d_analysis': 'lightblue',
            'llm_generation': 'lightgreen',
            'verifier': 'lightcoral',
            'manual_annotation': 'lightyellow'
        }

        node_colors = [color_map.get(self.evidences[node]['source'], 'lightgray')
                       for node in self.dependency_graph.nodes()]

        nx.draw(self.dependency_graph, pos, with_labels=True,
                node_color=node_colors, node_size=2000,
                font_size=8, font_weight='bold', arrows=True)

        plt.title("Evidence Dependency Graph")

        if output_path:
            plt.savefig(output_path)
        else:
            plt.show()