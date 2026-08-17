"""
树剪 — 统一脚本分割工具 (Script Utils)
================================================================
智能识别批量粘贴文本中的独立脚本边界，供批量生产和脚本学习库共用。

用法:
  from core.script_utils import split_scripts
  scripts = split_scripts(raw_text, force_by_line=False)
"""
import re
from typing import List

# 噪音/元数据行标记
_NOISE_TOKENS = {
    "D", "洗稿文案", "标题", "序号", "脚本", "文案", "备注",
    "ID", "id", "No", "no", "NO.",
}


def split_scripts(raw_text: str, force_by_line: bool = False) -> List[str]:
    """
    将原始文本智能分割成独立脚本列表。

    规则 (按优先级):
      1. force_by_line=True → 每行一个脚本。
      2. 含 Tab (\\t) → Excel多列粘贴 → 逐行取每行最长有效列。
      3. 默认 → 连续非空行合并为一个脚本，空行作为脚本分隔符。

    返回: 独立脚本字符串列表
    """
    if not raw_text or not raw_text.strip():
        return []

    if force_by_line:
        return _split_by_line(raw_text)

    # ── Tab分隔 → Excel多列粘贴 ──
    if "\t" in raw_text:
        result = []
        for line in raw_text.splitlines():
            col = _best_tab_column(line.strip())
            if col:
                clean = _clean_text(col)
                if _is_valid_script(clean):
                    result.append(clean)
        return _deduplicate_scripts(result)

    lines = raw_text.splitlines()
    non_empty = [l.strip() for l in lines if l.strip() and l.strip() not in _NOISE_TOKENS and len(l.strip()) >= 2]

    if not non_empty:
        return []

    # ── 有空行 → 按空行分组合并 ──
    has_blank = any(not l.strip() for l in lines)
    if has_blank:
        scripts = []
        current = []
        for line in lines:
            s = line.strip()
            if not s:
                if current:
                    script = "\n".join(current).strip()
                    if _is_valid_script(script):
                        scripts.append(script)
                    current = []
            else:
                if s not in _NOISE_TOKENS and len(s) >= 2:
                    current.append(s)
        if current:
            script = "\n".join(current).strip()
            if _is_valid_script(script):
                scripts.append(script)
        return _deduplicate_scripts(scripts) if scripts else []

    # ── 无空行无Tab: 启发式 → 每行独立有效则按行分, 否则全合并 ──
    all_independent = all(
        re.search(r'[一-鿿]', ln) and len(ln) >= 8
        for ln in non_empty
    )
    if all_independent and len(non_empty) >= 2:
        return _deduplicate_scripts([
            _clean_text(ln) for ln in non_empty if _is_valid_script(_clean_text(ln))
        ])

    # 默认全合并
    merged = "\n".join(non_empty).strip()
    return [merged] if _is_valid_script(merged) else []


def _split_by_line(raw_text: str) -> List[str]:
    """按行分割，Tab行取最长列"""
    lines = []
    for line in raw_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "\t" in s:
            s = _best_tab_column(s)
        s = _clean_text(s)
        if _is_valid_script(s):
            lines.append(s)
    return _deduplicate_scripts(lines)


def _best_tab_column(text: str) -> str:
    """从Tab分隔行中取包含中文或长度最长的有效列"""
    parts = [p.strip() for p in text.split("\t")]
    best = ""
    best_score = 0
    for p in parts:
        if not p or p in _NOISE_TOKENS:
            continue
        has_chinese = bool(re.search(r'[一-鿿]', p))
        score = len(p) + (100 if has_chinese else 0)
        if score > best_score:
            best_score = score
            best = p
    return best if best else text


def _clean_text(text: str) -> str:
    """去除噪音前后缀，合并多余空格"""
    text = text.strip()
    # 去掉开头的编号 (如 "1." "1、" "①")
    text = re.sub(r'^[\d]+[\.\)、．]?\s*', '', text)
    text = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩]?\s*', '', text)
    # 合并多余空白
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _is_valid_script(text: str) -> bool:
    """判断是否是一个有效的脚本 (v2: lowered threshold to 3)"""
    if len(text) < 3:
        return False
    if text in _NOISE_TOKENS:
        return False
    if text.startswith(("序号", "标题", "脚本", "文案", "备注")):
        return False
    return True


def _deduplicate_scripts(scripts: List[str]) -> List[str]:
    """去重 (保留顺序)"""
    seen = set()
    result = []
    for s in scripts:
        # 短哈希去重
        key = s[:40]
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result
