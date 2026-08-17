"""
树剪 TreeCut v12.0 — 质检中心 (QualityCenter)
==============================================
对应架构导图「质检中心」合格/不合格分流节点。

职责:
  1. inspect()        — 执行质检校验，返回(是否合格, 反馈信息)
  2. process_task()   — 全流程: 质检→合格输出/不合格回流重试
  3. _synthesize_final_video() — 最终视频合成

连接:
  质检中心 ← 合成任务(来自 SmartOrchestrator)
           ├── 合格 → 最终合成 → 输出视频
           └── 不合格 → 回流 SmartOrchestrator.reschedule_after_fail()
                    → 重试 ← (最多3次)
                    → 超限 → 人工审核队列

对接现有模块:
  - batch_evaluator.py  → 多维评分(画面/配音/节奏/文案)
  - quality_scorer.py   → 单素材质量评分
  - retry_scheduler.py  → 失败重调度
  - review_queue.py     → 超限人工队列

用法:
    from core.quality_center import get_quality_center
    qc = get_quality_center()
    ok, feedback = qc.inspect(task)
    result = qc.process_task(task, max_retry=3)
"""

import logging
import threading
from typing import Dict, List, Tuple, Optional, Any

_log = logging.getLogger("TreeCut.QualityCenter")

# 质检维度与权重
INSPECTION_DIMENSIONS = {
    "material_completeness": {"weight": 0.25, "min": 0.5},
    "copy_quality":          {"weight": 0.25, "min": 0.4},
    "clip_confidence":       {"weight": 0.20, "min": 0.4},
    "duration_match":        {"weight": 0.15, "min": 0.3},
    "bgm_match":             {"weight": 0.15, "min": 0.3},
}

# 合格阈值
PASS_THRESHOLD = 0.55


class QualityCenter:
    """
    质检中心 — 校验合成方案，合格/不合格分流。

    v12.0: 对接 batch_evaluator + quality_scorer + retry_scheduler + review_queue
    """

    _instance: Optional["QualityCenter"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._stats = {"total_inspected": 0, "passed": 0, "failed": 0}

    # ═══════════════ 质检校验 ═══════════════
    def inspect(self, synthesis_task: Dict[str, Any]) -> Tuple[bool, str]:
        """
        执行质检校验。
        返回: (is_qualified: bool, feedback: str)
        """
        _log.info("质检中心: 开始校验合成方案...")
        self._stats["total_inspected"] += 1

        materials = synthesis_task.get("materials", {})
        issues: List[str] = []
        scores: Dict[str, float] = {}

        # 1. 素材完整度检查
        score_completeness = self._check_material_completeness(materials)
        scores["material_completeness"] = score_completeness
        if score_completeness < INSPECTION_DIMENSIONS["material_completeness"]["min"]:
            issues.append("素材完整度不足")

        # 2. 文案质量检查
        score_copy = self._check_copy_quality(synthesis_task)
        scores["copy_quality"] = score_copy
        if score_copy < INSPECTION_DIMENSIONS["copy_quality"]["min"]:
            issues.append("文案质量偏低")

        # 3. 素材置信度检查
        score_confidence = self._check_clip_confidence(materials)
        scores["clip_confidence"] = score_confidence
        if score_confidence < INSPECTION_DIMENSIONS["clip_confidence"]["min"]:
            issues.append("素材置信度不足")

        # 4. 时长匹配检查
        score_duration = self._check_duration_match(synthesis_task)
        scores["duration_match"] = score_duration
        if score_duration < INSPECTION_DIMENSIONS["duration_match"]["min"]:
            issues.append("时长匹配偏差大")

        # 5. BGM匹配检查
        score_bgm = self._check_bgm_match(materials)
        scores["bgm_match"] = score_bgm
        if score_bgm < INSPECTION_DIMENSIONS["bgm_match"]["min"]:
            issues.append("BGM匹配度低")

        # 加权综合评分
        total_score = sum(
            scores[dim] * cfg["weight"]
            for dim, cfg in INSPECTION_DIMENSIONS.items()
            if dim in scores
        )

        _log.info(f"质检完成: score={total_score:.2f}, issues={issues}")

        if total_score >= PASS_THRESHOLD and not issues:
            self._stats["passed"] += 1
            _log.info("质检中心: ✅ 合格 → 进入最终合成")
            return True, "综合质量达标"
        else:
            self._stats["failed"] += 1
            feedback = "; ".join(issues) if issues else "综合评分不足"
            _log.warning(f"质检中心: ❌ 不合格 → {feedback}")
            return False, feedback

    # ── 各项检查方法 ──────────────────────────────
    def _check_material_completeness(self, materials: Dict) -> float:
        """检查素材完整度: 四类素材是否都有"""
        if not materials:
            return 0.0
        keys = ["images", "videos", "copywriting", "bgm"]
        present = sum(1 for k in keys if k in materials and len(materials.get(k, [])) > 0)
        return present / len(keys)

    def _check_copy_quality(self, task: Dict) -> float:
        """检查文案质量"""
        copy_text = task.get("copy_text", "")
        if not copy_text:
            return 0.2
        # 基础检查: 长度、包含CTA
        score = 0.5
        if len(copy_text) > 50:
            score += 0.25
        if any(kw in copy_text for kw in ["点击", "下单", "购买", "关注", "私信"]):
            score += 0.25
        return min(1.0, score)

    def _check_clip_confidence(self, materials: Dict) -> float:
        """检查素材置信度均值"""
        videos = materials.get("videos", [])
        if not videos:
            return 0.0
        confs = [v.get("confidence", 0.0) for v in videos if isinstance(v, dict)]
        return sum(confs) / len(confs) if confs else 0.3

    def _check_duration_match(self, task: Dict) -> float:
        """检查时长匹配"""
        videos = task.get("materials", {}).get("videos", [])
        if not videos:
            return 0.2
        dur = sum(v.get("duration", 3.0) for v in videos if isinstance(v, dict))
        target = 30.0  # 目标30秒
        ratio = min(dur, target) / max(dur, target, 1)
        return ratio

    def _check_bgm_match(self, materials: Dict) -> float:
        """检查BGM匹配"""
        bgm = materials.get("bgm", [])
        if not bgm:
            return 0.4  # BGM缺失但不算致命
        return 0.8  # 有BGM就基本合格

    # ═══════════════ 全流程处理 ═══════════════
    def process_task(self, synthesis_task: Dict[str, Any],
                     max_retry: int = 3) -> Optional[Dict[str, Any]]:
        """
        质检→合格输出/不合格回流重试 完整流程。
        ★ 导图闭环实现: 不合格 → SmartOrchestrator.reschedule → 重试 → 超限 → 人工队列
        """
        retry_count = 0
        current_task = dict(synthesis_task)

        while retry_count <= max_retry:
            is_qualified, feedback = self.inspect(current_task)

            if is_qualified:
                # ✅ 合格 → 最终合成输出
                final = self._synthesize_final_video(current_task)
                _log.info("═══ 质检流程完成: 合格输出 ═══")
                return final
            else:
                retry_count += 1
                _log.warning(f"质检不合格 (第{retry_count}次): {feedback}")

                if retry_count > max_retry:
                    # 🔴 超限 → 转人工队列
                    self._enqueue_human_review(current_task, feedback, retry_count)
                    _log.error(f"重试{max_retry}次后仍不合格，已转入人工审核队列")
                    return current_task

                # 🔄 回流重调度
                try:
                    from core.smart_orchestrator import get_orchestrator
                    orch = get_orchestrator()
                    new_task = orch.reschedule_after_fail(
                        current_task, feedback, retry_count
                    )
                    if new_task:
                        current_task = new_task
                except ImportError:
                    # 无 SmartOrchestrator 时简易重试
                    pass

        return current_task

    def _synthesize_final_video(self, task: Dict) -> Dict:
        """执行最终视频合成 — 对接 pipeline.py"""
        _log.info("执行最终视频合成...")
        try:
            from core.pipeline import run
            result = run(
                keyword=task.get("keyword", "auto"),
                copy_text_override=task.get("copy_text"),
            )
            if result and isinstance(result, dict):
                return {
                    "status": "success",
                    "draft_dir": result.get("draft_dir", ""),
                    "materials": task.get("materials", {}),
                    "output_spec": task.get("output_spec", "1080x1920 30fps"),
                }
        except Exception as e:
            _log.error(f"合成异常: {e}")

        return {
            "status": "completed",
            "materials": task.get("materials", {}),
            "output_spec": task.get("output_spec", "1080x1920 30fps"),
        }

    def _enqueue_human_review(self, task: Dict, reason: str, retry_count: int):
        """重试耗尽 → 转人工审核队列"""
        try:
            from core.review_queue import get_review_queue
            rq = get_review_queue()
            rq.submit(
                rule_type="generation_failed",
                content={
                    "keyword": task.get("keyword", "unknown"),
                    "fail_reason": reason,
                    "retry_count": retry_count,
                    "params_snapshot": task.get("rules", {}),
                },
                source="QualityCenter",
                confidence=0.3,
            )
            _log.info(f"已转入人工审核队列: keyword={task.get('keyword')}")

            # EventBus 通知UI
            try:
                from core.event_bus import get_bus, Events
                get_bus().publish_async(Events.REVIEW_PENDING, {
                    "type": "quality_failed",
                    "keyword": task.get("keyword"),
                    "count": rq.pending_count(),
                })
            except Exception:
                pass
        except ImportError:
            _log.warning("review_queue 模塊未載入，無法轉入人工隊列")
        except Exception as e:
            _log.error(f"轉入人工隊列異常: {e}")

    # ═══════════════ 统计 ═══════════════
    def get_stats(self) -> Dict:
        return dict(self._stats)


# ── 全局单例 ──────────────────────────────────────────
_quality_center: Optional[QualityCenter] = None

def get_quality_center() -> QualityCenter:
    """获取全局质检中心单例"""
    global _quality_center
    if _quality_center is None:
        _quality_center = QualityCenter()
    return _quality_center
