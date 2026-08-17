"""
树剪 — 自动主题发现引擎 v10.4
聚类素材密集字幕 → 发现热门主题 → 自动生成拍摄脚本
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import Counter


def discover_topics(embeddings: List[List[float]], labels: List[str] = None,
                    top_k: int = 5) -> List[Dict]:
    """聚类嵌入向量 → 返回热门主题列表"""
    if len(embeddings) < 2:
        return [{"topic": "默认主题", "keywords": ["岛台", "展示"],
                 "score": 1.0, "count": max(1, len(embeddings))}]

    try:
        from sklearn.cluster import KMeans
    except ImportError:
        return _fallback_topics(labels or [])

    X = np.array(embeddings, dtype=np.float32)
    n_clusters = min(top_k, len(embeddings))
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km.fit(X)

    topics = []
    for i in range(n_clusters):
        mask = km.labels_ == i
        count = int(np.sum(mask))
        center = km.cluster_centers_[i].tolist()

        # 从该簇的标签中提取关键词
        cluster_labels = []
        if labels:
            for j, lbl in enumerate(labels):
                if mask[j]:
                    cluster_labels.append(lbl)

        # 提取代表性关键词
        if cluster_labels:
            words = " ".join(cluster_labels).replace(",", " ").split()
            word_counts = Counter(w for w in words if len(w) >= 2)
            keywords = [w for w, _ in word_counts.most_common(8)]
        else:
            keywords = ["岛台素材", f"主题{i+1}"]

        topic_name = keywords[0] if keywords else f"主题{i+1}"

        topics.append({
            "topic": topic_name,
            "keywords": keywords[:8],
            "score": round(count / len(embeddings), 3),
            "count": count,
            "center": center
        })

    topics.sort(key=lambda t: -t["count"])
    return topics


def _fallback_topics(labels: List[str]) -> List[Dict]:
    """无 sklearn 时的降级方案 — 基于标签频率"""
    if not labels:
        return [{"topic": "岛台展示", "keywords": ["岛台", "展示", "设计"],
                 "score": 1.0, "count": 1}]
    all_words = " ".join(labels).replace(",", " ").split()
    word_counts = Counter(w for w in all_words if len(w) >= 2)
    top_words = [w for w, _ in word_counts.most_common(10)]
    return [{"topic": "热门主题", "keywords": top_words[:8],
             "score": 1.0, "count": len(labels)}]


def generate_script_from_topic(topic: Dict) -> str:
    """根据发现的主题自动生成口播脚本"""
    from core.copywriter import generate_copy, generate_fallback_copy
    try:
        keyword = " ".join(topic.get("keywords", ["岛台"])[:3])
        return generate_copy(keyword, 6, 28.0)
    except Exception:
        return generate_fallback_copy(topic.get("topic", "岛台展示"))
