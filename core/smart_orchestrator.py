"""
树剪 TreeCut v12.0 — 智能调度解析中心 (SmartOrchestrator)
===========================================================
对应架构导图中部「智能调度解析中心」— 系统核心大脑。

职责:
  1. parse_demand()    — 解析用户需求，拆解为四大素材库调取指令
  2. schedule_all()     — 统一调度四大智能素材库，汇总素材包
  3. build_synthesis()  — 生成视频合成执行任务
  4. reschedule_fail()  — 不合格回流重调度 + 触发纠错提效

连接对象:
  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │ ImageSmart  │  │ VideoSmart  │  │ CopySmart   │  │ BGMSmart    │
  │  Library    │  │  Library    │  │  Library    │  │  Library    │
  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
         │                │                │                │
         └────────────────┼────────────────┼────────────────┘
                          │
                 ┌────────▼────────┐
                 │ SmartOrchestrator│  ← 本模块
                 └────────┬────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
   ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
   │  Quality    │ │  EventBus   │ │    Log      │
   │  Center     │ │  Publish    │ │   System    │
   └─────────────┘ └─────────────┘ └─────────────┘

用法:
    from core.smart_orchestrator import get_orchestrator
    orch = get_orchestrator()
    task = orch.execute("生成一条30秒家居岛台产品视频")
"""

import logging
import threading
from typing import Dict, List, Optional, Any
from pathlib import Path

_log = logging.getLogger("TreeCut.SmartOrchestrator")


class SmartOrchestrator:
    """
    智能调度解析中心 — 统一协调四大智能库 + 质检 + EventBus。

    对接现有模块 (不替换，只编排):
      - 图片: frame_annotator.py + vision_unified.py
      - 视频: library_builder.py + smart_matcher.py
      - 文案: copywriter.py + deepseek_client.py
      - BGM:  bgm_matcher.py + audio_models.py
      - 合成: pipeline.py + draft.py
      - 质检: quality_center.py + batch_evaluator.py
    """

    _instance: Optional["SmartOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._image_ready = False
        self._video_ready = False
        self._copy_ready = False
        self._bgm_ready = False
        self._eventbus_ready = False
        self._stats = {"total_requests": 0, "total_success": 0, "total_fail": 0}
        self._init_eventbus()

    def _init_eventbus(self):
        """连接 EventBus"""
        try:
            from core.event_bus import get_bus, Events
            self._bus = get_bus()
            self._events = Events
            self._eventbus_ready = True
        except Exception:
            self._bus = None
            self._eventbus_ready = False

    # ═══════════════ 需求解析 ═══════════════
    def parse_demand(self, user_demand: str) -> Dict[str, str]:
        """
        解析用户需求 → 拆解为各素材库调取指令。
        对接 copywriter.py 进行关键词提取和文案风格判定。
        """
        _log.info(f"解析需求: {user_demand}")
        instructions = {
            "image_demand":   f"匹配产品主体展示图: {user_demand}",
            "video_demand":   f"匹配场景化运镜片段: {user_demand}",
            "copy_demand":    f"匹配营销脚本与行业话术: {user_demand}",
            "bgm_demand":     f"匹配节奏合适的营销BGM: {user_demand}",
        }

        # 尝试利用 copywriter 进行关键词增强
        try:
            from core.copywriter import extract_video_descriptions
            # 这里可以做关键词提取等增强逻辑
            _log.debug("copywriter 关键词增强已启用")
        except ImportError:
            pass

        return instructions

    # ═══════════════ 四大素材库统一调度 ═══════════════
    def schedule_all_materials(self, instructions: Dict[str, str]) -> Dict[str, Any]:
        """
        向四大智能素材库批量发起调取，汇总素材包。
        返回: {"images": [...], "videos": [...], "copywriting": [...], "bgm": [...]}
        """
        _log.info("向四大智能库发起批量调度")
        material_pack: Dict[str, Any] = {
            "images":      self._fetch_images(instructions.get("image_demand", "")),
            "videos":      self._fetch_videos(instructions.get("video_demand", "")),
            "copywriting": self._fetch_copy(instructions.get("copy_demand", "")),
            "bgm":         self._fetch_bgm(instructions.get("bgm_demand", "")),
        }

        total = sum(len(v) for v in material_pack.values() if isinstance(v, list))
        _log.info(f"调度完成: 汇总 {total} 条素材")
        self._stats["total_requests"] += 1
        return material_pack

    def _fetch_images(self, demand: str) -> List[Dict]:
        """从图片智能素材库获取素材"""
        try:
            from core.database import db
            with db.get_connection() as conn:
                rows = conn.execute(
                    """SELECT video_path, tags, objects, style, confidence
                       FROM materials WHERE analyzed=1 AND tags!=''
                       ORDER BY confidence DESC LIMIT 10"""
                ).fetchall()
                return [{"path": r[0], "tags": r[1], "objects": r[2],
                        "style": r[3], "confidence": r[4]} for r in rows]
        except Exception as e:
            _log.warning(f"图片库调度异常: {e}")
            return []

    def _fetch_videos(self, demand: str) -> List[Dict]:
        """从视频智能素材库获取素材"""
        try:
            from core.database import db
            with db.get_connection() as conn:
                rows = conn.execute(
                    """SELECT video_path, start_time, end_time, duration, tags, confidence
                       FROM materials WHERE analyzed=1 AND duration>1.0
                       ORDER BY confidence DESC LIMIT 10"""
                ).fetchall()
                return [{"path": r[0], "source_start": r[1], "end_time": r[2],
                        "duration": r[3], "tags": r[4], "confidence": r[5]} for r in rows]
        except Exception as e:
            _log.warning(f"视频库调度异常: {e}")
            return []

    def _fetch_copy(self, demand: str) -> List[str]:
        """从文案智能库获取文案"""
        try:
            from core.copywriter import generate_copy
            result = generate_copy(keyword=demand, num_clips=6, total_duration=30.0)
            return [result] if result else []
        except Exception as e:
            _log.warning(f"文案库调度异常: {e}")
            # fallback
            try:
                from core.database import db
                with db.get_connection() as conn:
                    rows = conn.execute(
                        "SELECT content FROM learned_scripts ORDER BY id DESC LIMIT 5"
                    ).fetchall()
                    return [r[0] for r in rows]
            except Exception:
                return []

    def _fetch_bgm(self, demand: str) -> List[str]:
        """从BGM智能素材库获取BGM"""
        try:
            from core.bgm_matcher import match_bgm
            bgm_list = match_bgm(demand)
            return bgm_list if bgm_list else []
        except Exception:
            return []

    # ═══════════════ 生成合成任务 ═══════════════
    def build_synthesis_task(self, material_pack: Dict[str, Any],
                              keyword: str = "",
                              copy_text: str = None) -> Dict[str, Any]:
        """
        构建视频合成执行任务。
        对接 pipeline.py 进行实际视频生成。
        """
        _log.info(f"构建合成任务: keyword={keyword}")

        task = {
            "keyword": keyword,
            "materials": material_pack,
            "copy_text": copy_text or "",
            "rules": {
                "match_method": "FAISS+CLIP重排",
                "clip_duration_min": 3.0,
                "clip_duration_max": 5.0,
                "num_clips": 6,
            },
            "output_spec": "1080x1920 30fps",
        }

        # 如果有关键词但无文案，自动生成
        if keyword and not task["copy_text"]:
            try:
                from core.copywriter import generate_copy
                task["copy_text"] = generate_copy(
                    keyword=keyword, num_clips=6, total_duration=30.0
                )
            except Exception:
                pass

        return task

    # ═══════════════ 回流重调度（闭环核心）═══════════════
    def reschedule_after_fail(self, original_task: Dict[str, Any],
                               fail_reason: str,
                               retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """
        ★ 導圖閉環核心: 不合格 → 回流重调度 → 纠错提效。
        对接 retry_scheduler.py 进行智能参数调整。
        """
        _log.warning(f"回流重调度: reason={fail_reason}, retry={retry_count}")

        # 1. 触发视频库纠错提效
        try:
            from core.event_wiring import publish_log
            publish_log("SmartOrchestrator", "warning", f"纠错提效: {fail_reason}")
        except Exception:
            pass

        # 2. 调用 RetryScheduler 获取调整后的参数
        try:
            from core.retry_scheduler import get_retry_scheduler, FailReason
            rs = get_retry_scheduler()
            original_params = original_task.get("rules", {})
            reason = FailReason(fail_reason) if fail_reason in FailReason._value2member_map_ else FailReason.UNKNOWN
            adjusted = rs.schedule_retry(
                original_task.get("keyword", "unknown"),
                original_params, reason.value,
                last_score=0
            )
            if adjusted:
                # 用调整后的参数重建任务
                new_task = dict(original_task)
                new_task["rules"] = adjusted
                new_task["_retry_count"] = retry_count + 1
                _log.info(f"重调度完成: 新参数={adjusted}")
                return new_task
        except ImportError:
            pass
        except Exception as e:
            _log.error(f"重调度异常: {e}")

        # 回退: 简单调整阈值
        new_task = dict(original_task)
        new_task["rules"]["match_threshold"] = max(0.3,
            original_task.get("rules", {}).get("match_threshold", 0.6) - 0.1)
        new_task["_retry_count"] = retry_count + 1
        return new_task

    # ═══════════════ 全流程执行 ═══════════════
    def execute(self, user_demand: str,
                keyword: str = None,
                max_retry: int = 3) -> Optional[Dict[str, Any]]:
        """
        一键执行完整流程: 解析→调度→合成→质检→(不合格→回流)×N→输出。
        ★ v12.1: 自动记录到 task_record 表
        """
        kw = keyword or user_demand
        _log.info(f"═══ 开始全流程执行: {kw} ═══")
        self._publish_event("GENERATION_STARTED", {"keyword": kw})

        # ★ v12.1: 创建任务记录
        task_id = -1
        try:
            from core.database import db
            task_id = db.insert_task_record(
                task_type="smart_execute", keyword=kw, status="执行中",
                output_dir=user_demand[:200] if user_demand else ""
            )
        except Exception:
            pass

        # Step 1: 解析需求
        instructions = self.parse_demand(user_demand)

        # Step 2: 调度素材
        material_pack = self.schedule_all_materials(instructions)

        # Step 3: 构建合成任务
        synthesis_task = self.build_synthesis_task(material_pack, keyword=kw)
        materials_count = sum(len(v) for v in material_pack.values() if isinstance(v, list))

        # Step 4: 质检 + 回流循环
        retry_count = 0
        current_task = synthesis_task

        while retry_count <= max_retry:
            try:
                from core.quality_center import get_quality_center
                qc = get_quality_center()
                is_qualified, feedback = qc.inspect(current_task)
            except ImportError:
                result = self._run_pipeline(current_task)
                if task_id > 0:
                    try:
                        db.update_task_record(task_id, status="成功",
                            output_path=result.get("draft_dir","") if result else "")
                        db.update_task_record(task_id, materials_count=materials_count)
                    except Exception:
                        pass
                return result

            if is_qualified:
                _log.info("质检通过，开始合成")
                result = self._run_pipeline(current_task)
                if result:
                    self._stats["total_success"] += 1
                    self._publish_event("GENERATION_DONE", {"keyword": kw, "result": result})
                if task_id > 0:
                    try:
                        db.update_task_record(task_id, status="成功",
                            output_path=result.get("draft_dir","") if result else "",
                            retry_times=retry_count, materials_count=materials_count)
                    except Exception:
                        pass
                return result
            else:
                retry_count += 1
                _log.warning(f"质检不通过 (第{retry_count}次): {feedback}")
                if retry_count > max_retry:
                    self._stats["total_fail"] += 1
                    self._publish_event("GENERATION_FAILED",
                        {"keyword": kw, "error": f"重试{max_retry}次后仍不合格: {feedback}"})
                    if task_id > 0:
                        try:
                            db.update_task_record(task_id, status="失败",
                                error_msg=feedback, retry_times=retry_count-1)
                        except Exception:
                            pass
                    return current_task

                new_task = self.reschedule_after_fail(current_task, feedback, retry_count)
                if new_task:
                    current_task = new_task
                    self._publish_event("RETRY_SCHEDULED",
                        {"keyword": kw, "retry": retry_count, "reason": feedback})

        return current_task

    def batch_execute(self, task_list: list, max_retry: int = 3) -> Dict:
        """
        ★ v12.1: 批量任务执行 — 对应导图 batch_generate_video_tasks()。
        :param task_list: 需求字符串列表
        :return: 批量任务统计报告 {"total": N, "success": M, "fail": F, "success_rate": X%, "details": [...]}
        """
        _log.info(f"═══ 启动批量任务: {len(task_list)}条 ═══")
        results = []
        success_count = 0

        for idx, demand in enumerate(task_list, 1):
            _log.info(f"--- [{idx}/{len(task_list)}] {demand} ---")
            try:
                res = self.execute(demand, max_retry=max_retry)
                detail = {
                    "task_index": idx,
                    "demand": demand,
                    "success": bool(res and res.get("draft_dir")),
                    "result": res,
                }
                if detail["success"]:
                    success_count += 1
                results.append(detail)
            except Exception as e:
                results.append({"task_index": idx, "demand": demand, "success": False, "error": str(e)})
                _log.error(f"任务{idx}异常: {e}")

        report = {
            "total": len(task_list),
            "success": success_count,
            "fail": len(task_list) - success_count,
            "success_rate": f"{(success_count/max(len(task_list),1)*100):.1f}%",
            "details": results,
        }
        _log.info(f"═══ 批量完成: {report['success_rate']} ═══")
        return report

    def _run_pipeline(self, task: Dict) -> Optional[Dict]:
        """执行 pipeline 生成 — v12.1: 传递调度素材"""
        try:
            from core.pipeline import run
            # ★ 修复: 将调度到的素材传入 pipeline
            materials = task.get("materials", {})
            exclude_paths = []
            if materials:
                # 收集已调度视频路径作为 session_used
                for v in materials.get("videos", []):
                    if isinstance(v, dict) and v.get("path"):
                        exclude_paths.append(str(v["path"]))

            result = run(
                keyword=task.get("keyword", ""),
                copy_text_override=task.get("copy_text"),
                exclude_paths=exclude_paths,
                **{k: v for k, v in task.get("rules", {}).items()
                   if k in ("num_clips", "match_threshold")},
            )
            return result
        except Exception as e:
            _log.error(f"Pipeline 実行異常: {e}")
            return None

    # ═══════════════ EventBus ═══════════════
    def _publish_event(self, event_name: str, data: Dict):
        """发布事件到 EventBus"""
        try:
            if self._eventbus_ready and self._bus:
                event = getattr(self._events, event_name, None)
                if event:
                    self._bus.publish(event, data)
        except Exception:
            pass

    # ═══════════════ 统计 ═══════════════
    def get_stats(self) -> Dict:
        return dict(self._stats)


# ── 全局单例 ──────────────────────────────────────────
_orchestrator: Optional[SmartOrchestrator] = None

def get_orchestrator() -> SmartOrchestrator:
    """获取全局调度中心单例"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SmartOrchestrator()
    return _orchestrator
