"""
树剪 — 批量自我评估引擎 v10.4
生成后自动评分 → 低于阈值自动重试/调整参数
"""
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class SelfEvaluator:
    """自我评估器 — 对生成结果进行多维度自动评分"""

    def __init__(self, min_score: float = 0.55, max_retries: int = 2):
        self.min_score = min_score
        self.max_retries = max_retries
        self.history: List[Dict] = []

    def evaluate(self, result: dict) -> Tuple[float, List[str]]:
        """综合评估生成结果，返回(评分, 问题列表)"""
        scores = {}
        issues = []

        # 1. 文案长度检查 (标准: 70-100字)
        copy_text = result.get("copy", "")
        copy_len = len(copy_text)
        if 70 <= copy_len <= 100:
            scores["copy_length"] = 0.9
        elif 50 <= copy_len <= 120:
            scores["copy_length"] = 0.6
            issues.append(f"文案长度偏差({copy_len}字)")
        else:
            scores["copy_length"] = 0.3
            issues.append(f"文案长度异常({copy_len}字)")

        # 2. CTA 检查
        from core.copywriter import check_cta_present
        if check_cta_present(copy_text):
            scores["cta"] = 0.95
        else:
            scores["cta"] = 0.4
            issues.append("缺少CTA行动引导")

        # 3. 素材数量检查
        clips = result.get("clips", [])
        if 5 <= len(clips) <= 10:
            scores["clip_count"] = 0.85
        elif len(clips) >= 3:
            scores["clip_count"] = 0.6
            issues.append(f"素材数量偏少({len(clips)}个)")
        else:
            scores["clip_count"] = 0.2
            issues.append(f"素材严重不足({len(clips)}个)")

        # 4. 总时长检查
        total_dur = result.get("total_duration", 0)
        if 23 <= total_dur <= 35:
            scores["duration"] = 0.9
        elif 15 <= total_dur <= 45:
            scores["duration"] = 0.65
            issues.append(f"时长偏差({total_dur:.0f}s)")
        else:
            scores["duration"] = 0.35
            issues.append(f"时长异常({total_dur:.0f}s)")

        # 5. TTS 一致性检查
        tts_dur = result.get("tts_duration", 0)
        if tts_dur > 0 and total_dur > 0:
            ratio = tts_dur / total_dur
            if 0.7 <= ratio <= 1.2:
                scores["tts_sync"] = 0.85
            else:
                scores["tts_sync"] = 0.5
                issues.append(f"配音与视频时长不匹配(比={ratio:.2f})")
        else:
            scores["tts_sync"] = 0.5

        # 加权综合评分
        weights = {"copy_length": 0.25, "cta": 0.30, "clip_count": 0.20,
                   "duration": 0.15, "tts_sync": 0.10}
        total = sum(scores.get(k, 0.5) * w for k, w in weights.items())

        self.history.append({"scores": scores, "total": round(total, 3),
                            "issues": issues})

        return round(total, 3), issues

    def should_retry(self, score: float, attempt: int) -> bool:
        """判断是否需要重试"""
        return score < self.min_score and attempt < self.max_retries

    def get_suggestions(self) -> List[str]:
        """根据历史记录生成优化建议"""
        if not self.history:
            return []
        avg = sum(h["total"] for h in self.history[-5:]) / len(self.history[-5:])
        suggestions = []
        if avg < 0.5:
            suggestions.append("建议检查素材库是否充足")
        if any(any("CTA" in issue for issue in h.get("issues", [])) for h in self.history[-3:]):
            suggestions.append("文案系统可能需要调整CTA模板")
        return suggestions

    def get_stats(self) -> dict:
        return {
            "evaluated": len(self.history),
            "avg_score": round(sum(h["total"] for h in self.history) / max(1, len(self.history)), 3),
            "retry_rate": sum(1 for h in self.history if h["total"] < self.min_score) / max(1, len(self.history)),
        }


# 全局实例
_evaluator: Optional[SelfEvaluator] = None


def get_evaluator() -> SelfEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = SelfEvaluator()
    return _evaluator
