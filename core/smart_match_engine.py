"""
树剪 TreeCut v11.6 — 自适应匹配引擎 (Layered Dedup)
====================================================
三层去重 + 脚本素材偏好学习 + 全局热度衰减 + 强制差异化

核心函数:
  get_adaptive_clips(query, num, session_used, script_hash, position)
  → 返回去重+偏好调整+热度衰减后的素材列表
"""

import hashlib, math
from pathlib import Path
from typing import List, Dict, Set, Optional

# 全局热度: usage_count -> 衰减因子
def _decay_factor(usage_count: int) -> float:
    """1 / (log(count+2) + 0.3) — 使用越多权重越低"""
    return 1.0 / (math.log(usage_count + 2) + 0.3)


def script_hash(text: str) -> str:
    """SHA256 前 16 位"""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def get_adaptive_clips(
    query: str,
    num_clips: int = 8,
    session_used: Set[str] = None,
    shash: str = None,
    position: str = "middle",
) -> List[Dict]:
    """
    自适应素材匹配，自动去重+偏好加权+热度衰减。

    返回:
      [{"path": Path, "source_start": float, "duration": float,
        "speed": float, "match_score": float, "match_method": str}, ...]
    """
    from material_engine_v3.core.smart_matcher import get_smart_matcher
    import sqlite3 as _sq

    sm = get_smart_matcher()
    session_used = session_used or set()
    main_db = str(Path(__file__).parent.parent / "ai_material_library.db")

    # ── Step 1: 基础匹配(3x候选) ──
    candidates = sm.search(query, top_k=num_clips * 3)
    if not candidates:
        return []

    # ── Step 2: 去重 + 评分调整 ──
    seen_ids = set()
    adjusted = []

    # v12.0 修复: 预取全部候选素材的统计数据 — 消除 N+1 查询
    all_vps = [c.get("video_path", "") for c in candidates if c.get("video_path")]
    all_stats = _get_all_material_stats(all_vps, shash)

    for c in candidates:
        vp = c.get("video_path", "")
        if not vp:
            continue

        # 强制去重 ─ 本次任务内绝不重复
        if vp in session_used:
            continue

        # 去重 ─ 同一视频不同段
        cid = f"{vp}:{c.get('start_time', 0)}"
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        base_score = float(c.get("score", 0.5))
        stats = all_stats.get(vp, {"pref": 0.5, "usage": 0, "opening": 0})

        # 脚本偏好加成
        pref = stats["pref"] if shash else 0.5
        base_score *= (0.7 + 0.5 * pref)

        # 全局热度衰减
        base_score *= _decay_factor(stats["usage"])

        # 位置差异化 ─ 开场素材额外降权已用过的
        if position == "opening" and stats["opening"] > 1:
            base_score *= 0.5  # 曾被用作开场的素材大幅降权

        c["adaptive_score"] = round(min(1.0, base_score), 3)
        c["match_method"] = c.get("match_method", "") + "+自适应"
        adjusted.append(c)

    # ── Step 3: 排序返回 ──
    adjusted.sort(key=lambda x: -x.get("adaptive_score", 0))

    return adjusted[:num_clips]


# v12.0 修复: 将3次独立查询合并为1次批量查询 — 消除 N+1 问题
_DB_PATH = str(Path(__file__).parent.parent / "ai_material_library.db")


def _get_all_material_stats(video_paths: list, shash: str = None) -> dict:
    """
    批量获取素材统计信息 — 单次连接, 3次查询, 替代 N*3 次连接。
    返回: {video_path: {"pref": float, "usage": int, "opening": int}}
    """
    result = {vp: {"pref": 0.5, "usage": 0, "opening": 0} for vp in video_paths}
    try:
        import sqlite3 as _sq
        with _sq.connect(_DB_PATH) as db:
            # 1. 偏好得分（批量）
            if shash:
                placeholders = ",".join("?" * len(video_paths))
                rows = db.execute(
                    f"SELECT material_path, avg_user_score, match_count "
                    f"FROM script_material_preference "
                    f"WHERE script_hash=? AND material_path IN ({placeholders})",
                    [shash] + list(video_paths)
                ).fetchall()
                for row in rows:
                    if row[1] and row[2] and row[2] > 0:
                        result[row[0]]["pref"] = min(0.95,
                            (float(row[1]) / 5.0) * min(1.0, row[2] / 30))

            # 2. 历史使用次数（批量）
            rows2 = db.execute(
                f"SELECT material_path, COUNT(*) FROM generation_material_log "
                f"WHERE material_path IN ({placeholders}) "
                f"GROUP BY material_path",
                list(video_paths)
            ).fetchall()
            for row in rows2:
                result[row[0]]["usage"] = row[1]

            # 3. 开场使用次数（批量）
            rows3 = db.execute(
                f"SELECT material_path, COUNT(*) FROM generation_material_log "
                f"WHERE material_path IN ({placeholders}) AND order_index=0 "
                f"GROUP BY material_path",
                list(video_paths)
            ).fetchall()
            for row in rows3:
                result[row[0]]["opening"] = row[1]

    except Exception:
        pass
    return result


def _get_pref_score(shash: str, video_path: str) -> float:
    """脚本对该素材的偏好得分 (0-1) — v12.0: 使用批量查询"""
    stats = _get_all_material_stats([video_path], shash)
    return stats.get(video_path, {}).get("pref", 0.5)


def _get_usage_count(video_path: str) -> int:
    """获取素材历史使用次数 — v12.0: 使用批量查询"""
    stats = _get_all_material_stats([video_path])
    return stats.get(video_path, {}).get("usage", 0)


def _get_opening_usage(video_path: str) -> int:
    """获取素材被用作开场的次数 — v12.0: 使用批量查询"""
    stats = _get_all_material_stats([video_path])
    return stats.get(video_path, {}).get("opening", 0)


def record_script_match(shash: str, material_path: str, user_score: float = None):
    """记录脚本-素材匹配"""
    try:
        import sqlite3 as _sq
        main_db = str(Path(__file__).parent.parent / "ai_material_library.db")
        with _sq.connect(main_db) as db:
            db.execute("""
                INSERT INTO script_material_preference
                (script_hash, material_path, match_count, avg_user_score, last_used_at)
                VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(script_hash, material_path) DO UPDATE SET
                    match_count = match_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
            """, (shash, material_path, user_score or 3.0))
    except Exception:
        pass


def convert_to_clips(results: List[Dict], num_clips: int) -> List[Dict]:
    """将匹配结果转为 pipeline 可用的 clips 格式"""
    import random
    from pathlib import Path
    from core.config import CLIP_DURATION_MIN, CLIP_DURATION_MAX

    clips = []
    for r in results[:num_clips]:
        duration = float(r.get("end_time", 5)) - float(r.get("start_time", 0))
        if duration <= 1.0:
            duration = random.uniform(CLIP_DURATION_MIN, CLIP_DURATION_MAX)
        clips.append({
            "path": Path(r["video_path"]),
            "source_start": float(r.get("start_time", 0)),
            "duration": min(duration, CLIP_DURATION_MAX),
            "speed": 1.0,
            "ai_matched": True,
            "match_score": r.get("adaptive_score", r.get("score", 0)),
            "match_method": r.get("match_method", "自适应匹配"),
        })
    return clips
