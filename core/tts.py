"""
╔══════════════════════════════════════════════════════════════╗
║  🎙  video_editor.tts_engine — AI配音引擎                 ║
║  Edge TTS 配音生成 + 文本清洗 + 保护词校验                 ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import asyncio
import concurrent.futures
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

from core.config import (
    TTS_OUTPUT_DIR, TTS_VOICE, TTS_VOICE_ALT, TTS_VOLUME,
    DEFAULT_VOICE_RATE, DEFAULT_VOICE_PITCH, TTS_MAX_RETRIES,
    PROTECTED_WORDS, CLEAN_PREFIX_SYMBOL,
    SUBTITLE_MAX_CHARS_PER_LINE, TTS_CHARS_PER_SEC,
)

# ═══════════════════════════════════════════════════════════════
# 保护词预处理
# ═══════════════════════════════════════════════════════════════

_PROTECTED_WORDS_BY_LEN = None


def _get_protected_words_sorted() -> list:
    """获取按长度降序排列的保护词列表"""
    global _PROTECTED_WORDS_BY_LEN
    if _PROTECTED_WORDS_BY_LEN is None:
        _PROTECTED_WORDS_BY_LEN = sorted(set(PROTECTED_WORDS), key=len, reverse=True)
    return _PROTECTED_WORDS_BY_LEN


def protect_text_for_tts(text: str) -> str:
    """文案预处理：保护产品词不被TTS引擎拆分朗读"""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    for word in _get_protected_words_sorted():
        spaced = ' '.join(list(word))
        if spaced in text:
            text = text.replace(spaced, word)
        spaced2 = ''.join(c + ' ' for c in word).strip()
        if spaced2 in text:
            text = text.replace(spaced2, word)
    return text


def strip_leading_junk(text: str) -> str:
    """清除文本中行首的数字、序号、特殊符号（MULTILINE模式）"""
    if not CLEAN_PREFIX_SYMBOL:
        return text
    text = re.sub(r'\[[^\]]*\]', '', text)
    text = re.sub(r'^[\s]*([\d]+[\.\,\))]\s*)+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*([一二三四五六七八九十]+[\.\,\))]\s*)+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*[#\*\->->↓↑▶▷►✓✔✗✘○●□■△▲☆★◇◆]+[\s]*', '', text, flags=re.MULTILINE)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    return text.strip()


def global_strip_numbers(text: str) -> str:
    """全局清除孤立数字编号"""
    if not CLEAN_PREFIX_SYMBOL:
        return text
    text = re.sub(r'([.！？])\s*[\d]+[\.\,\))]', r'\1', text)
    text = re.sub(r'([.！？])\s*[一二三四五六七八九十]+[\.\,\))]', r'\1', text)
    text = re.sub(r'[①-⑩]', '', text)
    text = re.sub(r'\([\d]+\)', '', text)
    text = re.sub(r'\b(No\.|#)[\d]+', '', text, flags=re.IGNORECASE)
    return text.strip()


def clean_text_for_tts(text: str) -> str:
    """全链路清洗：确保TTS只朗读有效正文"""
    text = protect_text_for_tts(text)
    text = strip_leading_junk(text)
    text = global_strip_numbers(text)
    text = re.sub(r'[🔴🟠🟡🟢🔵🟣⚫⚪⬛⬜🔶🔷🔸🔹🔻🔺]', '', text)
    text = re.sub(r'[①②③④⑤⑥⑦⑧⑨⑩]', '', text)
    text = re.sub(r'[➡⬆⬇✅❌⭐🌟✨🔥💯💥💫🎉🎊👍👎💪🙌👏🤝👋💡🎵🎶📢📣📌📍🔍]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'[,,]{2,}', ',', text)
    text = re.sub(r'[..]{2,}', '.', text)
    text = re.sub(r'^[.,！？,\.!?\s]+', '', text)
    text = re.sub(r'[.,！？,\.!?]+$', '', text)
    text = global_strip_numbers(text)
    text = strip_leading_junk(text)
    return text.strip()


def filter_non_speech_fragments(subtitles: List[str]) -> List[str]:
    """过滤无效字幕片段：纯数字、纯符号一律丢弃"""
    result = []
    for sub in subtitles:
        chinese_chars = len(re.findall(r'[一-鿿]', sub))
        if chinese_chars < 2:
            continue
        cleaned = strip_leading_junk(sub)
        if len(re.findall(r'[一-鿿]', cleaned)) >= 2:
            result.append(cleaned)
    return result if result else subtitles


def validate_tts_content(original: str, cleaned: str) -> Tuple[bool, str]:
    """配音前内容抽检"""
    orig_chinese = len(re.findall(r'[一-鿿]', original))
    cleaned_chinese = len(re.findall(r'[一-鿿]', cleaned))
    if orig_chinese > 10 and cleaned_chinese < orig_chinese * 0.7:
        return False, f"汉字丢失过多(原文{orig_chinese}字->清洗后{cleaned_chinese}字)"
    if cleaned_chinese < 5:
        return False, f"清洗后有效汉字不足({cleaned_chinese}字)"
    chinese_ratio = cleaned_chinese / max(len(cleaned), 1)
    if chinese_ratio < 0.3:
        return False, f"清洗后非中文占比过高(中文比{chinese_ratio:.0%})"
    return True, "OK"


def verify_word_integrity(original_text: str, tts_text: str) -> Tuple[bool, list]:
    """配音后校验：检查保护词是否保持完整"""
    broken = []
    for word in _get_protected_words_sorted():
        # 只检查原文中存在的保护词
        if word not in original_text:
            continue
        # 如果保护词完整出现在TTS文本中，说明没问题
        if word in tts_text:
            continue
        # 否则认为保护词被破坏（可能被拆分、被替换、被遗漏）
        broken.append(word)
    return len(broken) == 0, broken


def split_copy_to_subtitles(copy_text: str, num_clips: int = None) -> List[str]:
    """将文案按自然句子拆分成字幕片段"""
    MAX_CHARS = SUBTITLE_MAX_CHARS_PER_LINE
    text = re.sub(r'\n+', '', copy_text)
    text = re.sub(r'画面\d+[::]\s*', '', text)
    text = re.sub(r'\d+⃣\s*', '', text)
    text = re.sub(r'\s+', '', text).strip()
    if not text:
        return ["坤宝岛台"]

    raw_parts = re.split(r'([.。！？])', text)
    sentences = []
    i = 0
    while i < len(raw_parts):
        part = raw_parts[i].strip()
        if not part:
            i += 1; continue
        if part in '.。！？' and sentences:
            sentences[-1] += part
        elif part not in '.。！？' and len(part) >= 2:
            if i + 1 < len(raw_parts) and raw_parts[i + 1] in '.。！？':
                sentences.append(part + raw_parts[i + 1])
                i += 2; continue
            else:
                sentences.append(part)
        i += 1

    result = []
    for sentence in sentences:
        if len(sentence) <= MAX_CHARS:
            result.append(sentence)
        else:
            comma_parts = re.split(r'([,,,])', sentence)
            current = ""; j = 0
            while j < len(comma_parts):
                p = comma_parts[j].strip()
                if not p: j += 1; continue
                if p in ',,,' and current:
                    next_part = comma_parts[j+1].strip() if j+1 < len(comma_parts) else ""
                    if len(current) + len(next_part) + 1 <= MAX_CHARS:
                        current += "," + next_part; j += 2; continue
                    else:
                        result.append(current); current = ""; j += 1; continue
                elif p not in ',,,':
                    if len(current) + len(p) + 1 <= MAX_CHARS:
                        current = (current + "," + p) if current else p
                    else:
                        if current: result.append(current)
                        current = p
                j += 1
            if current: result.append(current)

    seen = set()
    final = []
    for s in result:
        s = s.strip().rstrip(',,,')
        if len(s) >= 2 and s not in seen:
            seen.add(s); final.append(s)
    if not final: return ["坤宝岛台"]

    final = [strip_leading_junk(s) for s in final]
    final = [s.strip() for s in final if s.strip()]
    final = filter_non_speech_fragments(final)
    return final if final else ["坤宝岛台"]


def estimate_tts_duration(text: str) -> float:
    """估算文本的TTS朗读时长"""
    clean = re.sub(r'[^一-鿿\w]', '', text)
    return max(1.0, len(clean) / TTS_CHARS_PER_SEC)


# ═══════════════════════════════════════════════════════════════
# Edge TTS 核心
# ═══════════════════════════════════════════════════════════════

def _generate_tts_core(text: str, voice: str, output_path: Path,
                       rate_str: str = "+0%", pitch_str: str = "+0Hz") -> bool:
    """核心配音生成（Edge TTS调用）— v2 修复事件循环冲突"""
    try:
        import edge_tts
        async def _gen():
            communicate = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
            await communicate.save(str(output_path))
        try:
            # 已有运行中的事件循环 → 在新线程中执行
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _gen())
                future.result(timeout=120)
        except RuntimeError:
            # 无运行中的事件循环 → 直接运行
            asyncio.run(_gen())
        return output_path.exists() and output_path.stat().st_size > 100
    except Exception:
        return False


def generate_tts_voiceover(copy_text: str, keyword: str,
                           voice: str = None) -> Optional[Path]:
    """使用 Edge TTS 生成 AI 配音"""
    if voice is None:
        voice = TTS_VOICE

    output_dir = Path(TTS_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_text = clean_text_for_tts(copy_text)
    valid, reason = validate_tts_content(copy_text, clean_text)
    if not valid:
        print(f"   !! 内容抽检未通过: {reason}")
        print(f"   🔄 使用原始文案重试(仅做基础清洗)...")
        clean_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', copy_text)
        clean_text = re.sub(r'^[\s.,！？,\.!?,\-\—]+', '', clean_text).strip()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw = re.sub(r'[^\w一-鿿]', '_', keyword)[:10]
    output_path = output_dir / f"配音_{safe_kw}_{timestamp}.mp3"

    rate_str = "+10%"
    pitch_str = f"{DEFAULT_VOICE_PITCH:+d}Hz"

    voices_to_try = [voice]
    if voice != TTS_VOICE_ALT:
        voices_to_try.append(TTS_VOICE_ALT)

    for attempt in range(TTS_MAX_RETRIES + 1):
        current_voice = voices_to_try[min(attempt, len(voices_to_try) - 1)]
        if attempt > 0:
            print(f"   🔄 第{attempt+1}次重试 (音色: {current_voice})...")
        if attempt == 0:
            print(f"   🎙 正在生成 AI 配音 (Edge TTS, {current_voice}, rate={rate_str})...")
            print(f"   📝 清洗后文案: {clean_text[:80]}...")
        success = _generate_tts_core(clean_text, current_voice, output_path,
                                     rate_str=rate_str, pitch_str=pitch_str)
        if not success:
            continue
        is_clean, broken_words = verify_word_integrity(copy_text, clean_text)
        if broken_words:
            print(f"   !! 检测到 {len(broken_words)} 个保护词可能被破坏: {broken_words[:3]}...")
        else:
            print(f"   ✅ 断句校验通过(保护词完整)")
        file_size_kb = output_path.stat().st_size / 1024
        print(f"   ✅ AI 配音生成完成: {output_path.name} ({file_size_kb:.0f}KB)")
        return output_path

    print(f"   ❌ 配音生成失败(已重试{TTS_MAX_RETRIES}次)")
    return None


def get_audio_duration_seconds(file_path: Path) -> float:
    """检测音频文件的实际时长"""
    try:
        from pyJianYingDraft.local_materials import AudioMaterial
        return AudioMaterial(str(file_path.absolute())).duration / 1_000_000
    except Exception:
        return 0


# ═══════════════ ★ v12.2: SRT字幕导出 ═══════════════
def subtitle_to_srt(subtitles: list, output_path: str) -> str:
    """
    将字幕列表导出为标准SRT字幕文件。
    subtitles: [{"start": 0.0, "end": 2.5, "text": "文案"}, ...]
    """
    from utils.helpers import format_srt_time

    lines = []
    for idx, sub in enumerate(subtitles, 1):
        start = format_srt_time(sub.get("start", 0))
        end = format_srt_time(sub.get("end", 0))
        text = sub.get("text", "")
        lines.append(f"{idx}\n{start} --> {end}\n{text}\n")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path.absolute())

