"""
树剪 TreeCut v12.0 — 基础素材库 (MaterialRegistry)
===================================================
对应架构导图左侧「基础库」— 统一管理所有原始输入素材。

职责:
  1. 注册/查询四类原始素材: 图片/视频/脚本/BGM
  2. 导入时自动记录来源和时间
  3. 提供统计摘要

连接:
  基础库 → 四大智能素材库(识别→入库)
         → 智能调度解析中心(调取)

用法:
    from core.material_registry import get_registry
    reg = get_registry()
    reg.import_materials(images=[...], videos=[...], scripts=[...], bgm=[...])
    summary = reg.get_summary()
"""

import json
import os
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

_log = logging.getLogger("TreeCut.MaterialRegistry")

_REGISTRY_FILE = Path(__file__).parent.parent / "material_registry.json"


class MaterialRegistry:
    """
    基础素材库 — 所有原始素材的统一注册中心。
    四类素材: product_images / video_materials / raw_scripts / bgm_tracks
    """

    _instance: Optional["MaterialRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._data: Dict[str, List[Dict]] = {
            "product_images":   [],
            "video_materials":  [],
            "raw_scripts":      [],
            "industry_info":    [],
            "bgm_tracks":       [],
        }
        self._load_from_disk()

    def _load_from_disk(self):
        """从持久化文件加载"""
        try:
            if _REGISTRY_FILE.exists():
                data = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
                with self._lock:
                    for key in self._data:
                        self._data[key] = data.get(key, [])
                _log.info(f"素材庫從文件加載: {_REGISTRY_FILE}")
        except Exception as e:
            _log.warning(f"素材庫加載失敗: {e}")

    def _save_to_disk(self):
        """持久化到文件"""
        try:
            with self._lock:
                _REGISTRY_FILE.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
        except Exception as e:
            _log.warning(f"素材庫保存失敗: {e}")

    # ═══════════════ 导入素材 ═══════════════
    def import_materials(self,
                         images: List[str] = None,
                         videos: List[str] = None,
                         scripts: List[str] = None,
                         industry: List[str] = None,
                         bgm: List[str] = None):
        """
        批量导入原始素材。
        每条素材自动附加: source(路径), imported_at(导入时间)。
        """
        with self._lock:
            if images:
                for path in images:
                    self._data["product_images"].append({
                        "source": str(path),
                        "type": "product_image",
                        "imported_at": datetime.now().isoformat(),
                    })
            if videos:
                for path in videos:
                    self._data["video_materials"].append({
                        "source": str(path),
                        "type": "video_material",
                        "imported_at": datetime.now().isoformat(),
                    })
            if scripts:
                for text in scripts:
                    self._data["raw_scripts"].append({
                        "content": text[:500],
                        "type": "script",
                        "imported_at": datetime.now().isoformat(),
                    })
            if industry:
                for info in industry:
                    self._data["industry_info"].append({
                        "content": info[:500],
                        "type": "industry_info",
                        "imported_at": datetime.now().isoformat(),
                    })
            if bgm:
                for path in bgm:
                    self._data["bgm_tracks"].append({
                        "source": str(path),
                        "type": "bgm_track",
                        "imported_at": datetime.now().isoformat(),
                    })

        total = (len(images or []) + len(videos or []) +
                 len(scripts or []) + len(industry or []) + len(bgm or []))
        _log.info(f"素材庫導入完成: +{total}條")
        self._save_to_disk()

        # EventBus 通知
        try:
            from core.event_bus import get_bus, Events
            get_bus().publish_async(Events.MATERIAL_UPDATED, {"imported": total})
        except Exception:
            pass

    # ═══════════════ 查询 ═══════════════
    def get_materials(self, category: str) -> List[Dict]:
        """获取某类素材"""
        with self._lock:
            return list(self._data.get(category, []))

    def get_all(self) -> Dict[str, List[Dict]]:
        """获取全部素材"""
        with self._lock:
            return {k: list(v) for k, v in self._data.items()}

    def get_summary(self) -> Dict[str, int]:
        """获取素材统计"""
        with self._lock:
            return {k: len(v) for k, v in self._data.items()}

    def get_total_count(self) -> int:
        """获取素材总数"""
        with self._lock:
            return sum(len(v) for v in self._data.values())

    # ═══════════════ 清空 ═══════════════
    def clear(self, category: str = None):
        """清空素材"""
        with self._lock:
            if category:
                self._data[category] = []
            else:
                for key in self._data:
                    self._data[key] = []
        self._save_to_disk()
        _log.info(f"素材庫已清空: {category or '全部'}")

    # ═══════════════ 统计信息 ═══════════════
    def print_summary(self):
        """打印统计摘要到控制台"""
        summary = self.get_summary()
        print("\n" + "=" * 50)
        print("  树剪 基础素材库 统计")
        print("  " + "-" * 40)
        print(f"  产品图片:     {summary['product_images']:>6} 条")
        print(f"  视频素材:     {summary['video_materials']:>6} 条")
        print(f"  原始脚本:     {summary['raw_scripts']:>6} 条")
        print(f"  行业信息:     {summary['industry_info']:>6} 条")
        print(f"  BGM音轨:      {summary['bgm_tracks']:>6} 首")
        print(f"  {'─' * 30}")
        print(f"  总计:         {sum(summary.values()):>6} 条")
        print("=" * 50)


# ── 全局单例 ──────────────────────────────────────────
_registry: Optional[MaterialRegistry] = None

def get_registry() -> MaterialRegistry:
    """获取全局素材库单例"""
    global _registry
    if _registry is None:
        _registry = MaterialRegistry()
    return _registry
