"""
树剪 TreeCut v12.2 — 多格式导出工具
===================================
支持: JSON/CSV/TXT 批量结果导出 + 统计报表生成。
"""
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from utils.helpers import time_cost


class ExportTool:
    """多格式导出 + 统计报表"""

    SUPPORTED = ["json", "csv", "txt"]

    @time_cost
    def export(self, results: List[Dict], output_path: str, fmt: str = "json") -> str:
        """导出结果到指定格式"""
        if fmt not in self.SUPPORTED:
            raise ValueError(f"不支持格式: {fmt}，可选: {self.SUPPORTED}")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        elif fmt == "csv":
            self._write_csv(results, path)
        elif fmt == "txt":
            path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

        return str(path.absolute())

    def _write_csv(self, results: List[Dict], path: Path):
        if not results:
            return
        keys = results[0].keys()
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)

    @staticmethod
    def batch_stats(results: List[Dict]) -> Dict:
        """
        批量任务统计 — 对应架构 batch_report。
        返回: {total, success, fail, success_rate, avg_duration, details}
        """
        total = len(results)
        success = sum(1 for r in results if r.get("success"))
        fail = total - success
        durations = [r.get("duration", 0) for r in results if r.get("success") and r.get("duration")]
        avg_dur = round(sum(durations) / len(durations), 1) if durations else 0

        return {
            "total": total,
            "success": success,
            "fail": fail,
            "success_rate": f"{(success / max(total, 1) * 100):.1f}%",
            "avg_duration_sec": avg_dur,
            "export_time": datetime.now().isoformat(),
        }

    @staticmethod
    def metrics_to_json(metrics: Dict, output_path: str = None) -> str:
        """将监控指标序列化为JSON字符串"""
        return json.dumps({
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
        }, ensure_ascii=False, indent=2)


_export_tool: Optional[ExportTool] = None

def get_export_tool() -> ExportTool:
    global _export_tool
    if _export_tool is None:
        _export_tool = ExportTool()
    return _export_tool
