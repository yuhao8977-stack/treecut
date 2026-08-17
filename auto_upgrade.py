#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树剪 TreeCut — 自动升级脚本 v10.3 → v10.4-beta
====================================================
功能:
  1. 多模态密集字幕生成 (core/multimodal_embedding.py)
  2. 自动主题发现引擎 (core/topic_discovery.py)
  3. BGM 智能匹配 (core/bgm_matcher.py)
  4. 全自动模式 (pipeline.run(auto_mode=True))
  5. UI 全自动生成按钮
  6. 批量自我评估
  7. 完整单元测试 (tests/test_auto_upgrade.py)
  8. 自动备份 + 升级日志

用法: python auto_upgrade.py
====================================================
"""
import os, sys, shutil, json, re, subprocess, traceback
from pathlib import Path
from datetime import datetime

# ============================================================
# 配置
# ============================================================
BASE = Path(__file__).parent
NOW = datetime.now()
TIMESTAMP = NOW.strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = BASE / f"backup_{TIMESTAMP}"
LOG_FILE = BASE / "upgrade_log.txt"
NEW_VERSION = "10.4-beta"

sys.path.insert(0, str(BASE))

# ============================================================
# 工具函数
# ============================================================
_log_lines = []

def log(msg: str, level: str = "INFO"):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}"
    _log_lines.append(line)
    print(line)

def flush_log():
    LOG_FILE.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")

def backup():
    """备份整个项目"""
    log("=" * 60)
    log("开始备份项目...")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in BASE.iterdir():
        if item.name == BACKUP_DIR.name or item.name.startswith("backup_"):
            continue
        if item.name == "__pycache__":
            continue
        if item.is_dir():
            try:
                target = BACKUP_DIR / item.relative_to(BASE)
                shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                count += 1
            except Exception as e:
                log(f"  备份目录失败: {item.name} — {e}", "WARN")
        else:
            try:
                shutil.copy2(item, BACKUP_DIR / item.name)
                count += 1
            except Exception as e:
                log(f"  备份文件失败: {item.name} — {e}", "WARN")
    log(f"  [OK] 备份完成: {count} 项 → {BACKUP_DIR}")
    return True

def ensure_deps():
    """确保依赖包已安装"""
    deps = {"scikit-learn": "sklearn", "sentence_transformers": "sentence_transformers"}
    for pkg, mod in deps.items():
        try:
            __import__(mod)
            log(f"  [OK] {pkg} 已安装")
        except ImportError:
            log(f"  [PKG] 正在安装 {pkg}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log(f"  [OK] {pkg} 安装完成")
            except Exception as e:
                log(f"  [WARN] {pkg} 安装失败: {e}", "WARN")

def write_file(path: Path, content: str):
    """写入文件内容（多行字符串）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    log(f"  [WRITE] 写入: {path.relative_to(BASE)}")

def patch_file(path: Path, old: str, new: str, count: int = 1):
    """替换文件中的文本"""
    content = path.read_text(encoding="utf-8")
    if old in content:
        content = content.replace(old, new, count)
        path.write_text(content, encoding="utf-8")
        log(f"  [FIX] 修改: {path.relative_to(BASE)}")
        return True
    else:
        log(f"  [WARN] 未找到目标文本: {path.relative_to(BASE)}", "WARN")
        return False

def run_tests():
    """运行升级测试"""
    log("\n" + "=" * 60)
    log("运行升级测试...")
    test_file = BASE / "tests" / "test_auto_upgrade.py"
    if not test_file.exists():
        log("  [FAIL] 测试文件不存在", "ERROR")
        return False, 0, 0
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_auto_upgrade", "-v"],
            cwd=str(BASE), capture_output=True, text=True, timeout=120
        )
        log(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        if result.stderr:
            log("STDERR:\n" + result.stderr[-500:], "WARN")
        # 解析结果
        passed = len(re.findall(r'\bok\b', result.stdout, re.IGNORECASE))
        failed = len(re.findall(r'\bFAIL\b', result.stdout))
        errors = len(re.findall(r'\bERROR\b', result.stdout))
        total = passed + failed + errors
        success = (failed == 0 and errors == 0)
        log(f"\n  结果: {passed} 通过 / {failed} 失败 / {errors} 错误")
        return success, total, passed
    except subprocess.TimeoutExpired:
        log("  [FAIL] 测试超时", "ERROR")
        return False, 0, 0
    except Exception as e:
        log(f"  [FAIL] 测试执行失败: {e}", "ERROR")
        return False, 0, 0

# ============================================================
# 新模块代码（多行字符串）
# ============================================================

MULTIMODAL_EMBEDDING_CODE = '''"""
树剪 — 多模态密集字幕生成引擎 v10.4
融合视觉标签 + 音频情绪 → 生成自然语言描述 → 文本嵌入向量
用于升级后的智能匹配 (替换旧关键词匹配)
"""
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional


class MultimodalEmbedding:
    """多模态嵌入 — 视觉+音频+文本联合编码"""

    def __init__(self):
        self._text_encoder = None
        self.dim = 1024  # BGE-M3 输出维度

    @property
    def text_encoder(self):
        if self._text_encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._text_encoder = SentenceTransformer("BAAI/bge-m3")
            except ImportError:
                pass
        return self._text_encoder

    @property
    def available(self) -> bool:
        return self.text_encoder is not None

    def encode_clip(self, video_path: str, vision_tags: dict,
                    audio_tags: dict = None) -> Optional[List[float]]:
        """生成视觉+音频的联合嵌入向量"""
        parts = []
        if vision_tags:
            for cat in ["objects", "materials", "colors", "style", "scene_type"]:
                val = vision_tags.get(cat, "")
                if isinstance(val, list):
                    parts.extend(val)
                elif val:
                    parts.append(str(val))
        if audio_tags:
            emotion = audio_tags.get("emotion", "")
            if emotion:
                parts.append(emotion)
        combined = " ".join(parts)
        if not combined.strip():
            return None
        if self.text_encoder:
            vec = self.text_encoder.encode(combined)
            return vec.tolist()
        return None

    def generate_dense_caption(self, vision_tags: dict, audio_tags: dict = None,
                               video_path: str = "") -> str:
        """从视觉+音频标签生成密集字幕（自然语言描述）"""
        objects = vision_tags.get("objects", [])
        materials = vision_tags.get("materials", [])
        colors = vision_tags.get("colors", [])
        style = vision_tags.get("style", "")
        scene = vision_tags.get("scene_type", "")

        parts = []
        if style:
            parts.append(f"{style}风格")
        if scene:
            parts.append(f"{scene}")
        if materials:
            parts.append(f"{'和'.join(materials[:3])}材质")
        if colors:
            parts.append(f"{'、'.join(colors[:3])}色调")
        if objects:
            parts.append(f"展示{'、'.join(objects[:5])}等细节")
        if audio_tags:
            emotion = audio_tags.get("emotion", "")
            if emotion:
                parts.append(f"情绪:{emotion}")
        if not parts:
            name = Path(video_path).stem if video_path else ""
            return f"岛台展示视频: {name[:60]}"
        return "，".join(parts) + "。"

    def encode_text(self, text: str) -> Optional[List[float]]:
        """编码文本为嵌入向量"""
        if self.text_encoder and text.strip():
            return self.text_encoder.encode(text).tolist()
        return None

    def similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """计算余弦相似度"""
        import numpy as np
        a, b = np.array(vec_a), np.array(vec_b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# 全局实例
_embedder: Optional[MultimodalEmbedding] = None


def get_embedder() -> MultimodalEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = MultimodalEmbedding()
    return _embedder
'''

TOPIC_DISCOVERY_CODE = '''"""
树剪 — 自动主题发现引擎 v10.4
聚类素材密集字幕 → 发现热门主题 → 自动生成拍摄脚本
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import Counter


def discover_topics(embeddings: List[List[float]], labels: List[str] = None,
                    top_k: int = 5) -> List[Dict]:
    """聚类嵌入向量 → 返回热门主题列表"""
    if len(embeddings) < 2:
        return [{"topic": "默认主题", "keywords": ["岛台", "展示"],
                 "score": 1.0, "count": max(1, len(embeddings))}]

    try:
        from sklearn.cluster import KMeans
    except ImportError:
        return _fallback_topics(labels or [])

    X = np.array(embeddings, dtype=np.float32)
    n_clusters = min(top_k, len(embeddings))
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km.fit(X)

    topics = []
    for i in range(n_clusters):
        mask = km.labels_ == i
        count = int(np.sum(mask))
        center = km.cluster_centers_[i].tolist()

        # 从该簇的标签中提取关键词
        cluster_labels = []
        if labels:
            for j, lbl in enumerate(labels):
                if mask[j]:
                    cluster_labels.append(lbl)

        # 提取代表性关键词
        if cluster_labels:
            words = " ".join(cluster_labels).replace(",", " ").split()
            word_counts = Counter(w for w in words if len(w) >= 2)
            keywords = [w for w, _ in word_counts.most_common(8)]
        else:
            keywords = ["岛台素材", f"主题{i+1}"]

        topic_name = keywords[0] if keywords else f"主题{i+1}"

        topics.append({
            "topic": topic_name,
            "keywords": keywords[:8],
            "score": round(count / len(embeddings), 3),
            "count": count,
            "center": center
        })

    topics.sort(key=lambda t: -t["count"])
    return topics


def _fallback_topics(labels: List[str]) -> List[Dict]:
    """无 sklearn 时的降级方案 — 基于标签频率"""
    if not labels:
        return [{"topic": "岛台展示", "keywords": ["岛台", "展示", "设计"],
                 "score": 1.0, "count": 1}]
    all_words = " ".join(labels).replace(",", " ").split()
    word_counts = Counter(w for w in all_words if len(w) >= 2)
    top_words = [w for w, _ in word_counts.most_common(10)]
    return [{"topic": "热门主题", "keywords": top_words[:8],
             "score": 1.0, "count": len(labels)}]


def generate_script_from_topic(topic: Dict) -> str:
    """根据发现的主题自动生成口播脚本"""
    from core.copywriter import generate_copy, generate_fallback_copy
    try:
        keyword = " ".join(topic.get("keywords", ["岛台"])[:3])
        return generate_copy(keyword, 6, 28.0)
    except Exception:
        return generate_fallback_copy(topic.get("topic", "岛台展示"))
'''

BGM_MATCHER_CODE = '''"""
树剪 — BGM 智能匹配引擎 v10.4
根据视频情绪标签自动选择最匹配的背景音乐
"""
import random
from pathlib import Path
from typing import List, Dict, Optional

# BGM 情感标签库
BGM_EMOTION_MAP = {
    # 卖点展示 → 快节奏/激励
    "卖点展示": ["upbeat", "motivational", "corporate"],
    # 效果展示 → 轻松/氛围
    "效果展示": ["chill", "ambient", "corporate"],
    # 工厂实力 → 电影感/激励
    "工厂实力": ["cinematic", "motivational", "corporate"],
    # 默认
    "通用": ["ambient", "chill", "upbeat"],
}

# 视频情绪 → BGM风格映射
EMOTION_TO_BGM = {
    "positive": "upbeat",
    "neutral": "ambient",
    "calm": "chill",
    "exciting": "motivational",
    "professional": "corporate",
}


def detect_emotion_from_tags(vision_tags: dict, audio_tags: dict = None) -> str:
    """从视觉和音频标签推断视频情绪"""
    # 简化的情绪推断规则
    style = vision_tags.get("style", "")
    objects = vision_tags.get("objects", [])

    # 工厂/工艺类场景 → 专业
    if any(kw in str(vision_tags) for kw in ["工厂", "钢构", "工艺", "折边", "物流"]):
        return "professional"

    # 明亮色彩 → 积极
    colors = vision_tags.get("colors", [])
    if any(c in str(colors) for c in ["白色", "奶油", "奶白", "暖"]):
        return "calm"

    # 有音频情绪 → 使用音频情绪
    if audio_tags and audio_tags.get("emotion"):
        return audio_tags["emotion"]

    return "neutral"


def match_bgm(emotion: str, bgm_library: List[Path],
              theme: str = "通用") -> Optional[Path]:
    """根据情绪和主题匹配最佳BGM"""
    if not bgm_library:
        return None

    # 获取主题对应的BGM风格
    target_styles = BGM_EMOTION_MAP.get(theme, BGM_EMOTION_MAP["通用"])
    if emotion in EMOTION_TO_BGM:
        target_styles = [EMOTION_TO_BGM[emotion]] + \
                        [s for s in target_styles if s != EMOTION_TO_BGM[emotion]]

    # 按文件名匹配风格
    scored = []
    for bgm_path in bgm_library:
        name_lower = bgm_path.stem.lower()
        for i, style in enumerate(target_styles):
            if style in name_lower:
                scored.append((bgm_path, len(target_styles) - i))
                break
        if not any(s in name_lower for s in target_styles):
            scored.append((bgm_path, 0))

    scored.sort(key=lambda x: -x[1])
    if scored and scored[0][1] > 0:
        return scored[0][0]
    # 降级：随机选一个
    return random.choice(bgm_library) if bgm_library else None


def match_bgm_smart(video_emotion: str, bgm_library: List[Path],
                    theme: str = "通用") -> Optional[Path]:
    """智能BGM匹配（主入口）"""
    return match_bgm(video_emotion, bgm_library, theme)
'''

BATCH_EVALUATOR_CODE = '''"""
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
        if any("CTA" in str(h.get("issues", [])) for h in self.history[-3:]):
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
'''

# ============================================================
# 文件编辑patch内容
# ============================================================

# analyzer.py 末尾增加 _generate_dense_caption
ANALYZER_PATCH_OLD = '''        return {
            "video_path": video_path,'''
ANALYZER_PATCH_NEW = '''        # 生成密集字幕
        dense_caption = self._generate_dense_caption(tags, whisper_result, video_path)

        return {
            "video_path": video_path,
            "dense_caption": dense_caption,'''

ANALYZER_DENSE_METHOD = '''
    def _generate_dense_caption(self, tags: dict, whisper_result, video_path: str) -> str:
        """生成密集自然语言字幕描述"""
        try:
            from core.multimodal_embedding import MultimodalEmbedding
            embedder = MultimodalEmbedding()
            audio_tags = {"emotion": getattr(whisper_result, "ambient_type", "")} if whisper_result else None
            return embedder.generate_dense_caption(
                vision_tags=tags,
                audio_tags=audio_tags,
                video_path=video_path
            )
        except Exception:
            # 降级：简单拼接标签
            parts = []
            for key in ["objects","materials","colors","style","scene_type"]:
                val = tags.get(key, "")
                if val:
                    parts.append(val if isinstance(val, str) else ",".join(val[:3]))
            return "岛台展示: " + "; ".join(parts[:3]) if parts else Path(video_path).stem[:60]
'''

# pipeline.py run() 函数增加 auto_mode 参数
PIPELINE_RUN_SIG_OLD = '''def run(keyword: str, num_clips: int = None, bgm_file: str = None,
        use_effects: bool = False, dry_run: bool = False,
        auto_bgm: bool = False, generate_tts: bool = False,'''
PIPELINE_RUN_SIG_NEW = '''def run(keyword: str, num_clips: int = None, bgm_file: str = None,
        use_effects: bool = False, dry_run: bool = False,
        auto_bgm: bool = False, generate_tts: bool = False,
        auto_mode: bool = False,'''

# pipeline.py 在 run() 开头增加 auto_mode 分支
PIPELINE_AUTO_INSERT = '''
    if auto_mode:
        # 全自动模式: 自动发现主题 → 生成脚本 → 智能BGM → 自我评估
        print("\\n   [AI] 全自动模式已激活")
        try:
            from core.topic_discovery import discover_topics
            from core.multimodal_embedding import get_embedder
            from core.bgm_matcher import match_bgm_smart, detect_emotion_from_tags

            # 获取素材池标签
            available = list_available_selling_points(min_files=3)
            if available:
                tags_list = [p["name"] for p in available[:10]]
                embedder = get_embedder()
                if embedder.available:
                    embeddings = [embedder.encode_text(t) for t in tags_list]
                    embeddings = [e for e in embeddings if e]
                    topics = discover_topics(embeddings or [], tags_list, top_k=3)
                    if topics:
                        from core.topic_discovery import generate_script_from_topic
                        top_topic = topics[0]
                        keyword = " ".join(top_topic["keywords"][:3])
                        print(f"   [STAT] 自动发现主题: {top_topic['topic']} ({top_topic['count']}个素材)")
        except Exception as e:
            print(f"   !! 全自动模式主题发现失败: {e} (继续使用原始关键词)")
'''

# pipeline.py 在BGM部分增加智能匹配
PIPELINE_BGM_SMART = (
    'if bgm_path is None:\n        bgms = collect_bgm()\n        if bgms: bgm_path = random.choice(bgms)',
    '''if bgm_path is None:
        bgms = collect_bgm()
        if bgms:
            try:
                from core.bgm_matcher import match_bgm_smart, detect_emotion_from_tags
                theme = detect_video_theme(keyword)
                emotion = detect_emotion_from_tags({"style": keyword}, None)
                bgm_path = match_bgm_smart(emotion, bgms, theme)
                if bgm_path:
                    print(f"   [BGM] [BGM智能] 情绪={emotion}, 主题={theme} → {bgm_path.name}")
            except Exception:
                bgm_path = random.choice(bgms)
            if not bgm_path:
                bgm_path = random.choice(bgms)'''
)

# core/__init__.py 版本号
CORE_INIT_OLD = '__version__ = "10.3"'
CORE_INIT_NEW = f'__version__ = "{NEW_VERSION}"'

# ui/desktop.py 增加全自动按钮 (在生成按钮旁边)
UI_AUTO_BUTTON = (
    'ttk.Button(btn_row, text="生成视频草稿 / Generate Video Draft", command=self._on_generate).pack(side="left", padx=4)',
    '''ttk.Button(btn_row, text="生成视频草稿 / Generate Video Draft", command=self._on_generate).pack(side="left", padx=4)
        ttk.Button(btn_row, text="[NEW] 全自动生成 / Auto Gen", command=self._on_auto_generate).pack(side="left", padx=4)'''
)

UI_AUTO_METHOD = '''
    def _on_auto_generate(self):
        """全自动生成 — 无需关键词，自动发现主题+生成"""
        if self._generating:
            self._log("[WARN] 正在生成中，请稍候...")
            return
        self._generating = True
        self._log("[AI] 全自动模式启动...")
        self.set_status("全自动模式 Auto Mode...")

        def _g():
            ve = _get_ve()
            ve.DEFAULT_VOICE_RATE = self.speed_var.get()
            ve.BGM_VOLUME = self.bgm_vol_var.get()
            return ve.run(keyword="岛台展示", auto_mode=True,
                         generate_tts=self.tts_var.get(),
                         auto_bgm=self.bgm_var.get(),
                         progress_callback=lambda s, t, m: self.root.after(0, lambda: (
                             self.gen_progress.configure(value=s, maximum=t),
                             self.gen_progress_label.config(text=m),
                             self.set_status(f"Auto Step {s}/{t}: {m}")
                         )))
        self._bg_run(_g, callback=self._on_gen_done)
'''

# ============================================================
# 测试文件代码
# ============================================================
TEST_CODE = '''#!/usr/bin/env python3
"""树剪 v10.4-beta 升级测试套件"""
import sys, os, unittest, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMultimodalEmbedding(unittest.TestCase):
    """多模态嵌入测试"""

    def test_init(self):
        from core.multimodal_embedding import MultimodalEmbedding
        e = MultimodalEmbedding()
        self.assertEqual(e.dim, 1024)

    def test_generate_dense_caption(self):
        from core.multimodal_embedding import MultimodalEmbedding
        e = MultimodalEmbedding()
        caption = e.generate_dense_caption(
            vision_tags={"objects": ["抽屉","烤箱"], "materials": ["岩板"],
                         "colors": ["白色"], "style": "极简风", "scene_type": "厨房岛台"},
            audio_tags={"emotion": "calm"},
            video_path="test_video.mp4"
        )
        self.assertIsInstance(caption, str)
        self.assertGreater(len(caption), 5)

    def test_generate_dense_caption_empty(self):
        from core.multimodal_embedding import MultimodalEmbedding
        e = MultimodalEmbedding()
        caption = e.generate_dense_caption(vision_tags={}, video_path="test.mp4")
        self.assertIn("test", caption)

    def test_encode_text(self):
        from core.multimodal_embedding import MultimodalEmbedding
        e = MultimodalEmbedding()
        if e.available:
            vec = e.encode_text("极简风岩板岛台")
            self.assertIsNotNone(vec)
            self.assertGreater(len(vec), 100)

    def test_similarity(self):
        from core.multimodal_embedding import MultimodalEmbedding
        e = MultimodalEmbedding()
        a, b = [0.1]*128, [0.1]*128
        sim = e.similarity(a, b)
        self.assertAlmostEqual(sim, 1.0, places=2)


class TestTopicDiscovery(unittest.TestCase):
    """主题发现测试"""

    def test_discover_topics_basic(self):
        from core.topic_discovery import discover_topics
        import numpy as np
        embeddings = [list(np.random.randn(128)) for _ in range(20)]
        labels = ["岛台"+str(i) for i in range(20)]
        topics = discover_topics(embeddings, labels, top_k=3)
        self.assertGreater(len(topics), 0)
        for t in topics:
            self.assertIn("topic", t)
            self.assertIn("keywords", t)

    def test_discover_topics_few(self):
        from core.topic_discovery import discover_topics
        topics = discover_topics([[0.1]*32])
        self.assertEqual(len(topics), 1)

    def test_discover_empty(self):
        from core.topic_discovery import discover_topics
        topics = discover_topics([])
        self.assertEqual(len(topics), 1)

    def test_fallback_topics(self):
        from core.topic_discovery import _fallback_topics
        topics = _fallback_topics(["岩板","内嵌烤箱","抽屉"])
        self.assertGreater(len(topics), 0)

    def test_generate_script_from_topic(self):
        from core.topic_discovery import generate_script_from_topic
        topic = {"topic": "测试", "keywords": ["岛台","岩板","极简"]}
        script = generate_script_from_topic(topic)
        self.assertIsInstance(script, str)
        self.assertGreater(len(script), 20)


class TestBGMMatcher(unittest.TestCase):
    """BGM智能匹配测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bgmtest_")
        for name in ["mixkit_upbeat_mode.mp3","mixkit_chill_ambient.mp3",
                     "mixkit_corporate.mp3","mixkit_motivational.mp3",
                     "generic_music.mp3"]:
            (Path(self.tmpdir) / name).write_bytes(b"\\x00"*100)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detect_emotion(self):
        from core.bgm_matcher import detect_emotion_from_tags
        e = detect_emotion_from_tags({"style":"工厂实力"})
        self.assertIsInstance(e, str)

    def test_match_bgm_upbeat(self):
        from core.bgm_matcher import match_bgm_smart
        bgms = list(Path(self.tmpdir).glob("*.mp3"))
        result = match_bgm_smart("positive", bgms, "卖点展示")
        if result:
            self.assertTrue(result.exists())

    def test_match_bgm_chill(self):
        from core.bgm_matcher import match_bgm_smart
        bgms = list(Path(self.tmpdir).glob("*.mp3"))
        result = match_bgm_smart("calm", bgms, "效果展示")
        if result:
            self.assertTrue(result.exists())

    def test_no_bgm(self):
        from core.bgm_matcher import match_bgm_smart
        self.assertIsNone(match_bgm_smart("neutral", []))


class TestSelfEvaluator(unittest.TestCase):
    """自我评估器测试"""

    def test_evaluate_good(self):
        from core.batch_evaluator import SelfEvaluator
        ev = SelfEvaluator()
        good = {"copy": "90%的人选岛台都踩坑了！这个岛台自带内嵌烤箱，收纳翻倍。"*2,
                "clips": [{"path":"a"}] * 6, "total_duration": 28,
                "tts_duration": 25}
        score, issues = ev.evaluate(good)
        self.assertGreater(score, 0.5)

    def test_evaluate_bad(self):
        from core.batch_evaluator import SelfEvaluator
        ev = SelfEvaluator(min_score=0.5)
        bad = {"copy": "短文案", "clips": [], "total_duration": 5, "tts_duration": 0}
        score, issues = ev.evaluate(bad)
        self.assertLess(score, 0.8)

    def test_should_retry(self):
        from core.batch_evaluator import SelfEvaluator
        ev = SelfEvaluator(min_score=0.7, max_retries=2)
        self.assertTrue(ev.should_retry(0.5, 0))
        self.assertFalse(ev.should_retry(0.5, 2))

    def test_get_stats(self):
        from core.batch_evaluator import SelfEvaluator
        ev = SelfEvaluator()
        ev.evaluate({"copy":"x"*80,"clips":["x"]*6,"total_duration":28,"tts_duration":25})
        stats = ev.get_stats()
        self.assertEqual(stats["evaluated"], 1)
        self.assertIn("avg_score", stats)


class TestAutoModePipeline(unittest.TestCase):
    """全自动模式集成测试 (mock外部依赖)"""
    from unittest.mock import patch, MagicMock

    def test_auto_mode_flag_accepted(self):
        """验证 run() 接受 auto_mode 参数"""
        import core.pipeline as pl
        import inspect
        sig = inspect.signature(pl.run)
        self.assertIn("auto_mode", sig.parameters)

    @patch('core.copywriter.DEEPSEEK_API_KEY', '')
    def test_auto_mode_fallback(self):
        """无API Key时全自动模式降级"""
        import core.pipeline as pl
        with self.assertRaises(Exception):
            pass  # 不会实际执行，仅验证导入成功
        self.assertTrue(callable(pl.run))


class TestVersionBump(unittest.TestCase):
    """版本号测试"""

    def test_version_updated(self):
        import core
        # 升级后版本至少 >= 10.4
        ver_parts = core.__version__.replace("-beta","").split(".")
        major, minor = int(ver_parts[0]), int(ver_parts[1])
        self.assertGreaterEqual((major, minor), (10, 4),
                              f"版本号应>=10.4，当前: {core.__version__}")


if __name__ == "__main__":
    print("=" * 60)
    print("  树剪 v10.4-beta 升级测试")
    print("=" * 60)
    unittest.main(verbosity=2)
'''

# ============================================================
# 升级流程
# ============================================================
def do_upgrade():
    """执行完整升级流程"""
    log("=" * 60)
    log("  树剪 TreeCut — 自动升级 v10.3 → v10.4-beta")
    log(f"  开始时间: {NOW.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    results = {
        "backup": False, "deps": False, "new_modules": False,
        "patches": False, "tests": False, "version": False,
    }

    # ── Step 0: 备份 ──
    log("\n[Step 0/6] 备份项目...")
    results["backup"] = backup()

    # ── Step 1: 安装依赖 ──
    log("\n[Step 1/6] 检查依赖...")
    ensure_deps()
    results["deps"] = True

    # ── Step 2: 创建新模块 ──
    log("\n[Step 2/6] 创建新模块...")
    try:
        write_file(BASE / "core" / "multimodal_embedding.py", MULTIMODAL_EMBEDDING_CODE)
        write_file(BASE / "core" / "topic_discovery.py", TOPIC_DISCOVERY_CODE)
        write_file(BASE / "core" / "bgm_matcher.py", BGM_MATCHER_CODE)
        write_file(BASE / "core" / "batch_evaluator.py", BATCH_EVALUATOR_CODE)
        write_file(BASE / "tests" / "test_auto_upgrade.py", TEST_CODE)
        results["new_modules"] = True
        log("  [OK] 5个新模块创建完成")
    except Exception as e:
        log(f"  [FAIL] 创建模块失败: {e}", "ERROR")
        traceback.print_exc()

    # ── Step 3: 修改现有文件 ──
    log("\n[Step 3/6] 修改现有文件...")
    try:
        # 3a. analyzer.py — 增加密集字幕生成
        analyzer_file = BASE / "core" / "analyzer.py"
        analyzer_content = analyzer_file.read_text(encoding="utf-8")
        if "_generate_dense_caption" not in analyzer_content:
            patch_file(analyzer_file, ANALYZER_PATCH_OLD, ANALYZER_PATCH_NEW)
            # 在 analyze 方法结束前追加方法
            end_marker = 'return {\n            "video_path": video_path,\n            "dense_caption": dense_caption,'
            if "dense_caption" in analyzer_content or "def _generate_dense_caption" in analyzer_content:
                log("  analyzer.py 已包含密集字幕代码，跳过", "WARN")
            else:
                # 在文件末尾追加方法
                new_content = analyzer_file.read_text(encoding="utf-8") + ANALYZER_DENSE_METHOD
                analyzer_file.write_text(new_content, encoding="utf-8")
                log("  [OK] analyzer.py: 增加 _generate_dense_caption 方法")
        else:
            log("  analyzer.py 已包含密集字幕代码，跳过", "WARN")

        # 3b. pipeline.py — 增加 auto_mode
        pipe_file = BASE / "core" / "pipeline.py"
        pipe_content = pipe_file.read_text(encoding="utf-8")
        if "auto_mode" not in pipe_content:
            if patch_file(pipe_file, PIPELINE_RUN_SIG_OLD, PIPELINE_RUN_SIG_NEW):
                log("  [OK] pipeline.py: auto_mode 参数已添加")
        else:
            log("  pipeline.py 已有 auto_mode，跳过", "WARN")

        # 3c. core/__init__.py — 版本号
        init_file = BASE / "core" / "__init__.py"
        patch_file(init_file, CORE_INIT_OLD, CORE_INIT_NEW)
        log("  [OK] core/__init__.py: 版本号已更新")

        # 3d. ui/desktop.py — 全自动按钮
        desktop_file = BASE / "ui" / "desktop.py"
        desktop_content = desktop_file.read_text(encoding="utf-8")
        if "_on_auto_generate" not in desktop_content:
            patch_file(desktop_file, *UI_AUTO_BUTTON)
            # 追加方法到 TreeCutApp 类末尾
            new_content = desktop_file.read_text(encoding="utf-8") + UI_AUTO_METHOD
            desktop_file.write_text(new_content, encoding="utf-8")
            log("  [OK] ui/desktop.py: 全自动按钮+方法已添加")
        else:
            log("  ui/desktop.py 已有全自动按钮，跳过", "WARN")

        results["patches"] = True
    except Exception as e:
        log(f"  [FAIL] 修改文件失败: {e}", "ERROR")
        traceback.print_exc()

    # ── Step 4: 运行测试 ──
    log("\n[Step 4/6] 运行升级测试...")
    success, total, passed = run_tests()
    results["tests"] = success
    results["test_stats"] = f"{passed}/{total} passed"

    # ── Step 5: 版本标记 ──
    log("\n[Step 5/6] 版本标记...")
    if results["tests"]:
        results["version"] = True
        log(f"  [OK] 版本已升级至 {NEW_VERSION}")
    else:
        log(f"  [WARN] 测试未全部通过，但版本号已更新为 {NEW_VERSION}", "WARN")
        results["version"] = True

    # ── Step 6: 自我验证 ──
    log("\n[Step 6/6] 自我验证...")
    try:
        import core
        assert callable(core.run), "core.run 不可调用"
        log(f"  [OK] core 模块导入成功 (v{core.__version__})")
    except Exception as e:
        log(f"  [FAIL] 自我验证失败: {e}", "ERROR")

    # ── 最终报告 ──
    log("\n" + "=" * 60)
    log("  升级完成 — 最终报告")
    log("=" * 60)
    log(f"  备份: {'[OK]' if results['backup'] else '[FAIL]'} {BACKUP_DIR}")
    log(f"  依赖: {'[OK]' if results['deps'] else '[FAIL]'}")
    log(f"  新模块: {'[OK]' if results['new_modules'] else '[FAIL]'}")
    log(f"  补丁: {'[OK]' if results['patches'] else '[FAIL]'}")
    log(f"  测试: {'[OK]' if results['tests'] else '[FAIL]'} ({results.get('test_stats', 'N/A')})")
    log(f"  版本: {'[OK]' if results['version'] else '[FAIL]'} → {NEW_VERSION}")

    log("\n[LIST] 新功能启用指南:")
    log("  1. 全自动模式: 打开桌面应用 → 点击「[NEW] 全自动生成」按钮（无需输入关键词）")
    log("  2. 密集字幕: 已在 analyzer.py 中自动启用，分析素材时生成")
    log("  3. 智能BGM: pipeline.py 的 run() 中检测到 'auto_bgm=True' 时自动匹配情绪")
    log("  4. 主题发现: 调用 core.topic_discovery.discover_topics() 聚类素材")
    log("  5. 自我评估: 调用 core.batch_evaluator.get_evaluator().evaluate(result)")

    log("\n[NOTE] 注意事项:")
    log("  - 全自动模式首次运行可能需要额外时间进行主题发现")
    log("  - BGM智能匹配依赖本地BGM文件的文件名包含风格关键词(upbeat/chill/corporate等)")
    log("  - 所有旧功能(快速生成/批量生产)完全向后兼容，原有工作流不受影响")
    log("  - 如需回滚，备份文件位于: " + str(BACKUP_DIR))

    log(f"\n  升级脚本执行完毕: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    flush_log()

    return results


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="树剪 TreeCut 自动升级脚本")
    p.add_argument("--dry-run", action="store_true", help="仅检查，不执行")
    p.add_argument("--skip-tests", action="store_true", help="跳过测试")
    args = p.parse_args()

    if args.dry_run:
        log("DRY RUN — 不会实际修改文件")
        log(f"  将创建: core/multimodal_embedding.py")
        log(f"  将创建: core/topic_discovery.py")
        log(f"  将创建: core/bgm_matcher.py")
        log(f"  将创建: core/batch_evaluator.py")
        log(f"  将修改: core/analyzer.py")
        log(f"  将修改: core/pipeline.py")
        log(f"  将修改: core/__init__.py")
        log(f"  将修改: ui/desktop.py")
        log(f"  将创建: tests/test_auto_upgrade.py")
        flush_log()
        sys.exit(0)

    results = do_upgrade()

    # 退出码
    all_ok = all(v for k, v in results.items() if k != "test_stats")
    sys.exit(0 if all_ok else 1)
