#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  🏝️  坤宝岛台 · 双程序检索复查复盘系统                      ║
║                                                            ║
║  独立运行: python review_audit.py --full                   ║
║  快速检查: python review_audit.py --quick                  ║
║  深度审计: python review_audit.py --deep                   ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys, os, json, sqlite3, re, argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE = Path(__file__).parent
AI_DB = BASE / "ai_material_library.db"
DRAFT_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / r"JianyingPro\User Data\Projects\com.lveditor.draft"
REPORT_OUT = BASE / "audit_report.json"


class AuditEngine:
    """全维度审查引擎"""

    def __init__(self):
        self.findings = {"critical": [], "high": [], "medium": [], "low": [], "info": []}
        self.metrics = {}

    # ── 维度1: 素材库健康度 ──
    def audit_material_health(self):
        if not AI_DB.exists():
            self.findings["critical"].append("AI素材库数据库不存在，需执行 python ai_material_library.py --build")
            return

        with sqlite3.connect(str(AI_DB)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
            with_tags = conn.execute("SELECT COUNT(*) FROM materials WHERE tags != ''").fetchone()[0]
            with_speech = conn.execute("SELECT COUNT(*) FROM materials WHERE speech_text != ''").fetchone()[0]
            videos = conn.execute("SELECT COUNT(*) FROM video_registry").fetchone()[0]
            analyzed = conn.execute("SELECT COUNT(*) FROM video_registry WHERE analyzed=1").fetchone()[0]

        self.metrics["material_health"] = {
            "total_segments": total,
            "tagged_segments": with_tags,
            "speech_segments": with_speech,
            "tag_coverage": f"{with_tags/max(total,1)*100:.1f}%",
            "speech_coverage": f"{with_speech/max(total,1)*100:.1f}%",
            "analyzed_videos": f"{analyzed}/{videos}",
        }

        if with_tags / max(total, 1) < 0.3:
            self.findings["high"].append(f"标签覆盖率仅{with_tags/max(total,1)*100:.0f}%，建议运行视觉分析worker提升质量")
        if with_speech / max(total, 1) < 0.1:
            self.findings["medium"].append(f"语音覆盖率仅{with_speech/max(total,1)*100:.0f}%，多数素材为无声展示视频(正常)")

    # ── 维度2: 标签质量 ──
    def audit_tag_quality(self):
        if not AI_DB.exists(): return

        with sqlite3.connect(str(AI_DB)) as conn:
            all_tags = conn.execute("SELECT tags FROM materials WHERE tags != ''").fetchall()
            all_styles = conn.execute("SELECT style FROM materials WHERE style != ''").fetchall()

        tag_counter = Counter()
        for (t,) in all_tags:
            for tag in t.split(","):
                if tag.strip(): tag_counter[tag.strip()] += 1

        style_counter = Counter()
        for (s,) in all_styles:
            for style in s.split(","):
                if style.strip(): style_counter[style.strip()] += 1

        self.metrics["tag_quality"] = {
            "unique_tags": len(tag_counter),
            "top_tags": tag_counter.most_common(10),
            "top_styles": style_counter.most_common(10),
        }

        if len(tag_counter) < 10:
            self.findings["high"].append(f"仅{len(tag_counter)}个不同标签，素材多样性严重不足")
        elif len(tag_counter) < 30:
            self.findings["medium"].append(f"标签种类{len(tag_counter)}个，建议扩大识别范围")

    # ── 维度3: 草稿质量 ──
    def audit_draft_quality(self):
        if not DRAFT_DIR.exists():
            self.findings["medium"].append("剪映草稿目录不存在")
            return

        drafts = sorted([d for d in DRAFT_DIR.iterdir() if d.is_dir()],
                        key=lambda x: x.stat().st_mtime, reverse=True)

        if not drafts:
            self.findings["info"].append("草稿箱为空，请先生成测试视频")
            return

        latest = drafts[0]
        content_file = latest / "draft_content.json"
        if not content_file.exists():
            self.findings["high"].append(f"最新草稿 {latest.name} 缺少 draft_content.json")
            return

        try:
            # 剪映草稿可能很大或加密 — 安全读取
            file_size = content_file.stat().st_size
            if file_size > 50 * 1024 * 1024:  # >50MB 可疑
                self.findings["info"].append(f"草稿文件过大({file_size/1024/1024:.0f}MB)，跳过解析")
                return
            with open(content_file, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read(8192)  # 读前8K足够判断格式
            stripped = raw.strip()
            if stripped.startswith("{"):
                # 尝试完整解析（限10MB以内）
                if file_size < 10 * 1024 * 1024:
                    with open(content_file, "r", encoding="utf-8") as f:
                        draft = json.load(f)
                else:
                    draft = json.loads(stripped[:100000]) if len(stripped) > 100 else {"_truncated": True}
                tracks = draft.get("tracks", [])
                video_segs = sum(1 for t in tracks if t.get("type") == "video" for _ in t.get("segments", []))
                text_segs = sum(1 for t in tracks if t.get("type") == "text" for _ in t.get("segments", []))
                audio_segs = sum(1 for t in tracks if t.get("type") == "audio" for _ in t.get("segments", []))
                self.metrics["draft_quality"] = {
                    "latest_draft": latest.name,
                    "video_segments": video_segs,
                    "text_segments": text_segs,
                    "audio_segments": audio_segs,
                    "duration": draft.get("duration", 0) / 1_000_000,
                }
                if text_segs < 3:
                    self.findings["high"].append(f"仅{text_segs}条字幕，可能断句有问题")
            elif stripped.startswith("\x1f\x8b") or len(stripped) < 10:
                self.findings["info"].append("草稿文件已压缩或加密(正常)，需在剪映中打开检查")
            else:
                self.findings["info"].append(f"草稿格式未知(首字符: {stripped[:1]})")
        except json.JSONDecodeError:
            self.findings["low"].append("草稿JSON格式损坏，可能正在剪映中编辑")
        except Exception as e:
            self.findings["low"].append(f"草稿解析异常: {str(e)[:80]}")

    # ── 维度4: 系统完整性 ──
    def audit_system_integrity(self):
        checks = {
            "主入口 树剪.py": (BASE / "树剪.py").exists(),
            "core/__init__.py": (BASE / "core" / "__init__.py").exists(),
            "core/pipeline.py": (BASE / "core" / "pipeline.py").exists(),
            "AI数据库": AI_DB.exists(),
            "FAISS索引": (BASE / "shipin" / "material_faiss.index").exists(),
            "配置文件 .env": (BASE / ".env").exists() or (BASE / ".env.example").exists(),
        }
        self.metrics["system_integrity"] = {k: "OK" if v else "MISSING" for k, v in checks.items()}
        missing = [k for k, v in checks.items() if not v]
        if missing:
            self.findings["critical"].append(f"缺失组件: {', '.join(missing)}")

    # ── 综合评分 ──
    def compute_score(self) -> dict:
        score = 100
        score -= len(self.findings["critical"]) * 25
        score -= len(self.findings["high"]) * 15
        score -= len(self.findings["medium"]) * 8
        score -= len(self.findings["low"]) * 3
        score = max(0, score)

        grade = "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D"

        total_issues = sum(len(v) for v in self.findings.values())
        return {
            "score": score, "grade": grade, "total_issues": total_issues,
            "breakdown": {k: len(v) for k, v in self.findings.items()},
        }

    def run_full(self):
        print("\n" + "=" * 55)
        print("  坤宝岛台 · 全量审查中...")
        print("=" * 55)

        print("  [1/4] 素材库健康度...")
        self.audit_material_health()
        print("  [2/4] 标签质量...")
        self.audit_tag_quality()
        print("  [3/4] 草稿质量...")
        self.audit_draft_quality()
        print("  [4/4] 系统完整性...")
        self.audit_system_integrity()

        score = self.compute_score()
        self.metrics["score"] = score

        # 生成报告
        report = {
            "timestamp": datetime.now().isoformat(),
            "findings": self.findings,
            "metrics": self.metrics,
            "score": score,
            "optimization_plan": self._generate_optimization_plan(),
        }

        with open(REPORT_OUT, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self._print_report(report)
        return report

    def _generate_optimization_plan(self) -> list:
        """根据发现的问题自动生成优化计划"""
        plan = []
        for severity, items in self.findings.items():
            for item in items:
                plan.append({
                    "issue": item,
                    "severity": severity,
                    "priority": "P0" if severity in ("critical", "high") else "P1" if severity == "medium" else "P2",
                    "suggested_action": self._suggest_action(item),
                })
        plan.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[x["severity"]])
        return plan

    def _suggest_action(self, issue: str) -> str:
        if "数据库不存在" in issue: return "运行: python ai_material_library.py --build"
        if "标签覆盖" in issue: return "运行: python -m modules.task_scheduler --vision"
        if "FAISS" in issue: return "运行: python -m modules.task_scheduler --index"
        if "API" in issue: return "运行: python -m modules.task_scheduler --serve"
        if "字幕" in issue: return "检查 split_copy_to_subtitles() 函数"
        if "缺失" in issue: return "检查对应文件是否存在"
        if "素材多样性" in issue: return "启用 --no-b-group 的反向开关 或 增加卖点文件夹"
        return "需要人工检查"

    def _print_report(self, report: dict):
        s = report["score"]
        f = report["findings"]
        m = report["metrics"]
        plan = report["optimization_plan"]

        print("\n" + "=" * 55)
        print(f"  综合评分: {s['score']}/100 ({s['grade']}级)")
        print(f"  问题总数: {s['total_issues']} (严重{s['breakdown']['critical']}/高{s['breakdown']['high']}/中{s['breakdown']['medium']}/低{s['breakdown']['low']})")
        print("=" * 55)

        if f["critical"]:
            print(f"\n  🔴 严重 ({len(f['critical'])}项)")
            for i in f["critical"]: print(f"    - {i}")
        if f["high"]:
            print(f"\n  🟠 重要 ({len(f['high'])}项)")
            for i in f["high"]: print(f"    - {i}")
        if f["medium"]:
            print(f"\n  🟡 中等 ({len(f['medium'])}项)")
            for i in f["medium"]: print(f"    - {i}")

        if m.get("material_health"):
            h = m["material_health"]
            print(f"\n  📊 素材库: {h['analyzed_videos']}视频, {h['total_segments']}片段, 标签覆盖{h['tag_coverage']}")

        print(f"\n  📋 优化计划 (TOP 5):")
        for i, p in enumerate(plan[:5]):
            print(f"    {i+1}. [{p['priority']}] {p['issue'][:60]}")
            print(f"       → {p['suggested_action']}")

        print("\n" + "=" * 55)
        print(f"  完整报告: {REPORT_OUT}")
        print("=" * 55 + "\n")


def main():
    parser = argparse.ArgumentParser(description="坤宝岛台 审查复查系统")
    parser.add_argument("--full", action="store_true", help="全量审查")
    parser.add_argument("--quick", action="store_true", help="快速检查(仅系统完整性)")
    parser.add_argument("--deep", action="store_true", help="深度审计(全量+标签质量)")
    args = parser.parse_args()

    engine = AuditEngine()

    if args.quick:
        print("快速系统检查...")
        engine.audit_system_integrity()
        s = engine.compute_score()
        print(f"\n评分: {s['score']}/100 ({s['grade']}级)")
    elif args.deep or args.full:
        engine.run_full()
    else:
        engine.run_full()


if __name__ == "__main__":
    main()
