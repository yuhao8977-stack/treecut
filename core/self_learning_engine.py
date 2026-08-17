"""
树剪 — 自学习引擎
每天自动分析使用记录 → DeepSeek生成优化规则 → 应用到各模块
"""
import os, json, time, threading, schedule
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from collections import defaultdict

RULES_DIR = Path("AI素材库/自学习规则")
RULES_DIR.mkdir(parents=True, exist_ok=True)


class SelfLearningEngine:
    """自学习引擎 — 定时分析+规则生成+自动应用"""

    def __init__(self):
        self._running = False
        self._thread = None
        self._last_run: Optional[datetime] = None

    def run_now(self) -> Dict:
        """立即执行一次完整自学习流程"""
        from core.usage_recorder import get_recorder
        from core.deepseek_client import get_deepseek

        recorder = get_recorder()
        ds = get_deepseek()

        report = {
            "timestamp": datetime.now().isoformat(),
            "status": "started",
            "records_analyzed": 0,
            "rules_generated": 0,
            "details": [],
        }

        # 1. 获取近期记录
        records = recorder.get_recent(500)
        if not records:
            report["status"] = "no_records"
            report["details"].append("没有使用记录，跳过学习")
            return report

        report["records_analyzed"] = len(records)

        # 按类型分类
        by_type = defaultdict(list)
        for r in records:
            by_type[r.get("type", "other")].append(r)

        # 2. DeepSeek分析标注记录 → 标签优化规则
        annotations = by_type.get("annotation", []) + by_type.get("scoring", [])
        if annotations and ds.available:
            result = ds.analyze_usage_records(annotations[-50:])
            if result:
                rule_file = RULES_DIR / f"label_rules_{datetime.now().strftime('%Y%m%d')}.txt"
                rule_file.write_text(result, encoding="utf-8")
                recorder.add_learning_rule("标签优化", result, "DeepSeek", 0.8)
                report["rules_generated"] += 1
                report["details"].append(f"标签优化规则已生成: {rule_file.name}")

        # 3. DeepSeek分析脚本修改 → 脚本风格规则
        scripts = by_type.get("script", []) + by_type.get("generation", [])
        if scripts and ds.available:
            result = ds.analyze_usage_records(scripts[-50:])
            if result:
                rule_file = RULES_DIR / f"script_rules_{datetime.now().strftime('%Y%m%d')}.txt"
                rule_file.write_text(result, encoding="utf-8")
                recorder.add_learning_rule("脚本风格", result, "DeepSeek", 0.75)
                report["rules_generated"] += 1
                report["details"].append(f"脚本风格规则已生成: {rule_file.name}")

        # 4. 自动调整模型权重
        scoring = by_type.get("scoring", [])
        if scoring and ds.available:
            result = ds.auto_adjust_weights(scoring[-100:])
            if result:
                self._apply_weight_rules(result)
                rule_file = RULES_DIR / f"weight_rules_{datetime.now().strftime('%Y%m%d')}.txt"
                rule_file.write_text(result, encoding="utf-8")
                recorder.add_learning_rule("模型权重", result, "DeepSeek", 0.85)
                report["rules_generated"] += 1
                report["details"].append(f"权重调整规则已生成: {result}")

        # 5. 分析脚本学习库 (高频词/风格偏好/句式模式)
        try:
            from core.script_learning import get_library
            lib = get_library()
            stats = lib.get_stats()
            if stats["total_scripts"] > 0:
                analysis = lib.analyze_patterns()
                if analysis:
                    rule_file = RULES_DIR / f"script_patterns_{datetime.now().strftime('%Y%m%d')}.txt"
                    rule_file.write_text(analysis, encoding="utf-8")
                    recorder.add_learning_rule("脚本风格分析", analysis, "DeepSeek", 0.7)
                    report["rules_generated"] += 1
                    report["details"].append(f"脚本库分析规则已生成: {rule_file.name} ({stats['total_scripts']}条脚本)")
        except Exception as e:
            report["details"].append(f"脚本库分析跳过: {e}")

        # 6. 生成综合报告
        summary = self._generate_summary(report, by_type)
        summary_file = RULES_DIR / f"learning_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        summary_file.write_text(summary, encoding="utf-8")
        report["details"].append(f"综合报告: {summary_file.name}")

        report["status"] = "completed"
        self._last_run = datetime.now()

        # 7. 清理30天前的旧规则
        self._cleanup_old_rules(30)

        return report

    def _apply_weight_rules(self, weight_text: str):
        """应用权重规则到配置文件 — 带范围+总和校验"""
        import re
        weights = {}
        for line in weight_text.strip().split("\n"):
            if ":" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        name = parts[0].strip()
                        val = float(re.sub(r'[^\d.]', '', parts[1].strip()))
                        # 校验: 单个权重必须在 0.0–1.0 之间
                        if 0.0 <= val <= 1.0:
                            weights[name] = round(val, 3)
                    except (ValueError, Exception):
                        pass
        if weights:
            # 校验: 权重总和在合理范围 (0.9–1.1)
            total = sum(weights.values())
            if not (0.9 <= total <= 1.1):
                from utils.logging import log_warning
                log_warning('self_learning_engine', f'权重总和={total} 超出合理范围, 跳过应用')
                return
            config_path = Path("AI素材库/model_weights.json")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if config_path.exists():
                try: existing = json.loads(config_path.read_text(encoding="utf-8"))
                except Exception as _e: from utils.logging import log_warning; log_warning('self_learning_engine', str(_e)[:80])
            existing.update({"updated": datetime.now().isoformat(), "weights": weights})
            config_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    def _generate_summary(self, report: Dict, by_type: dict) -> str:
        lines = ["=" * 50, "  树剪 AI 自学习报告",
                 f"  时间: {report['timestamp'][:19]}", f"  分析记录: {report['records_analyzed']}条",
                 f"  生成规则: {report['rules_generated']}条", "=" * 50, ""]
        for t, records in by_type.items():
            lines.append(f"  {t}: {len(records)}条记录")
        lines.append(f"\n规则文件位置: {RULES_DIR}")
        lines.append(f"最新规则请查看上述目录中的 .txt 文件")
        return "\n".join(lines)

    def _cleanup_old_rules(self, days: int = 30):
        cutoff = datetime.now() - timedelta(days=days)
        try:
            for f in RULES_DIR.glob("*.txt"):
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
        except Exception as _e: from utils.logging import log_warning; log_warning('self_learning_engine', str(_e)[:80])

    def start_scheduled(self, time_str: str = "02:00"):
        """启动定时学习 (每天指定时间)"""
        if self._running:
            return
        self._running = True

        def _run():
            schedule.every().day.at(time_str).do(self.run_now)
            while self._running:
                schedule.run_pending()
                time.sleep(60)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop_scheduled(self):
        self._running = False

    def get_latest_report(self) -> Optional[str]:
        """获取最新学习报告"""
        reports = sorted(RULES_DIR.glob("learning_report_*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)
        if reports:
            return reports[0].read_text(encoding="utf-8")
        return None

    def get_latest_rules(self, category: str = None) -> List[Dict]:
        """获取最新优化规则"""
        from core.usage_recorder import get_recorder
        rules = get_recorder().get_learning_rules()
        if category:
            rules = [r for r in rules if r["category"] == category]
        return rules[:20]


# 全局单例
_engine: Optional[SelfLearningEngine] = None

_engine_lock = __import__('threading').Lock()

def get_learning_engine() -> SelfLearningEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = SelfLearningEngine()
    return _engine
