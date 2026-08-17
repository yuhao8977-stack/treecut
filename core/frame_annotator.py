"""
树剪 — 全帧标注引擎 v4.0 (流式)
抽帧即显 + 后台模型识别 + 实时标签更新 + 静默子进程
"""
import os, sys, json, time, sqlite3, threading, tempfile, shutil
from utils.silent_subprocess import run as _silent_run
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class FrameAnnotation:
    frame_index: int = 0
    timestamp_sec: float = 0.0
    timestamp_str: str = "00:00:00.00"
    frame_path: str = ""
    model_tags: Dict[str, List[str]] = field(default_factory=dict)
    user_tags: List[str] = field(default_factory=list)
    edited: bool = False
    score: int = 3
    score_note: str = ""


class AnnotDB:
    """标注数据库"""
    def __init__(self, db_path="ai_material_library.db"):
        self.db_path = db_path; self._init()
    def _init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS video_annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT, video_name TEXT, frame_index INTEGER,
                    timestamp_str TEXT, frame_path TEXT, tags TEXT,
                    model_tags TEXT, score INTEGER DEFAULT 3, score_note TEXT,
                    edited INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS annotation_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT, old_tag TEXT, new_tag TEXT,
                    score INTEGER DEFAULT 3, user_note TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS tag_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT UNIQUE, correct_count INTEGER DEFAULT 0,
                    total_count INTEGER DEFAULT 0, accuracy REAL DEFAULT 0.0,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
    def save_frame(self, video_path, video_name, ann):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""INSERT OR REPLACE INTO video_annotations
                (video_path,video_name,frame_index,timestamp_str,frame_path,tags,model_tags,score,score_note,edited)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (video_path, video_name, ann.frame_index, ann.timestamp_str, ann.frame_path,
                 ",".join(ann.user_tags), json.dumps(ann.model_tags, ensure_ascii=False),
                 ann.score, ann.score_note, 1 if ann.edited else 0))
    def save_feedback(self, video_path, old_tag, new_tag, score, note=""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO annotation_feedback (video_id,old_tag,new_tag,score,user_note) VALUES (?,?,?,?,?)",
                        (video_path, old_tag, new_tag, score, note))
    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM video_annotations").fetchone()[0]
            edited = conn.execute("SELECT COUNT(*) FROM video_annotations WHERE edited=1").fetchone()[0]
            fb = conn.execute("SELECT COUNT(*) FROM annotation_feedback").fetchone()[0]
            return {"total_frames": total, "edited_frames": edited, "feedback_count": fb}
    def get_learning_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT tag, correct_count, total_count, accuracy FROM tag_learning ORDER BY accuracy DESC LIMIT 20").fetchall()
            return [{"tag":r[0],"correct":r[1],"total":r[2],"accuracy":r[3]} for r in rows]
    def update_learning(self, tag, is_correct):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""INSERT INTO tag_learning (tag,correct_count,total_count,accuracy,last_updated)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(tag) DO UPDATE SET
                correct_count=correct_count+?, total_count=total_count+1,
                accuracy=CAST(correct_count+? AS REAL)/CAST(total_count+1 AS REAL),
                last_updated=CURRENT_TIMESTAMP""",
                (tag, 1 if is_correct else 0, 1 if is_correct else 0, 1 if is_correct else 0))


class FrameAnnotator:
    """全帧标注引擎 v4.0 — 流式抽帧+识别"""

    def __init__(self, progress_callback=None, frame_ready_callback=None,
                 tag_ready_callback=None):
        """
        progress_callback(msg, pct)  — 全局进度
        frame_ready_callback(frame_annotation) — 新帧就绪（含图片路径，立即调）
        tag_ready_callback(frame_index, model_tags, user_tags) — 标签识别完成
        """
        self.progress_callback = progress_callback
        self.frame_ready_callback = frame_ready_callback
        self.tag_ready_callback = tag_ready_callback
        self._cancel = False
        self._frames = []
        self._video_path = ""
        self._video_name = ""
        self._temp_dir = ""
        self._models = []
        self._db = AnnotDB()
        self._vision = None
        self._speech_text = ""

    @property
    def frames(self): return self._frames
    @property
    def video_name(self): return self._video_name
    def cancel(self): self._cancel = True

    def _report(self, msg, pct=0):
        if self.progress_callback:
            self.progress_callback(msg, pct)

    # ═══════════════════════════════════════
    # Step 1: 抽帧 (快速，低分辨率)
    # ═══════════════════════════════════════
    def extract_frames(self, video_path, interval=2.0, max_frames=30, low_res=True):
        """FFmpeg抽帧 — 2s间隔, 30帧上限, 640宽低分辨率, 静默"""
        self._video_path = video_path
        self._video_name = Path(video_path).stem
        self._frames = []
        self._cancel = False
        self._temp_dir = tempfile.mkdtemp(prefix=f"tf_{self._video_name}_")
        self._report(f"抽帧中 (间隔{interval}s, 上限{max_frames})...", 0.02)
        try:
            dur = self._get_duration(video_path)
            if dur <= 0: self._report("无法获取视频时长", 0); return 0
            actual_interval = max(interval, dur / max_frames)
            out_pattern = os.path.join(self._temp_dir, "f_%05d.jpg")
            vf = f"fps=1/{actual_interval}"
            if low_res: vf += ",scale=640:-1"
            _silent_run(
                ["ffmpeg","-y","-i",video_path,"-vf",vf,"-q:v","2",
                 "-frames:v", str(max_frames), out_pattern],
                capture_output=True, timeout=60)
            frame_files = sorted(Path(self._temp_dir).glob("f_*.jpg"))
            for i, fp in enumerate(frame_files):
                if self._cancel: break
                ts = i * actual_interval
                ann = FrameAnnotation(
                    frame_index=i, timestamp_sec=round(ts, 2),
                    timestamp_str=self._fmt_ts(ts), frame_path=str(fp))
                self._frames.append(ann)
                # 每抽一帧立即回调 UI 显示
                if self.frame_ready_callback:
                    self.frame_ready_callback(ann)
                self._report(f"抽帧 {i+1}/{len(frame_files)}", 0.02 + 0.08 * ((i+1)/max(len(frame_files),1)))
            self._report(f"抽帧完成: {len(self._frames)}帧", 0.10)
            return len(self._frames)
        except Exception as e:
            self.cleanup()  # Clean up temp dir on failure
            self._report(f"抽帧失败: {e}", 0); return 0

    def extract_quick_test(self, video_path):
        return self.extract_frames(video_path, interval=2.0, max_frames=10, low_res=True)

    # ═══════════════════════════════════════
    # Step 2: 模型初始化 (后台)
    # ═══════════════════════════════════════
    def init_models(self) -> List[str]:
        """初始化所有模型，返回可用模型列表"""
        self._models = []
        try:
            from core.vision_unified import VisionModel
            self._vision = VisionModel()
            if self._vision.available:
                self._models.append(self._vision._loaded or "VisionModel")
        except Exception: pass  # Model unavailable — non-critical
        self._models.append("KnowledgeBridge")
        # Whisper
        self._speech_text = ""
        try:
            from core.audio_models import WhisperModel
            w = WhisperModel()
            if w.available:
                self._models.append("Whisper")
                result = w.transcribe(self._video_path)
                self._speech_text = result.transcript
        except Exception: pass  # Model unavailable — non-critical
        self._report(f"模型就绪: {self._models}", 0.12)
        return self._models

    # ═══════════════════════════════════════
    # Step 3: 流式识别 (并发, 每完成一帧立即回调)
    # ═══════════════════════════════════════
    def run_models_streaming(self, max_workers=2):
        """并发识别所有帧 — 每完成一帧立即通过 tag_ready_callback 通知UI"""
        if not self._frames: return 0
        if not self._vision:
            self.init_models()
        total = len(self._frames)
        done = [0]

        def _recognize_one(ann: FrameAnnotation) -> FrameAnnotation:
            if self._cancel: return ann
            # VisionModel
            if self._vision and self._vision.available:
                try:
                    r = self._vision.analyze(ann.frame_path)
                    tags = r.get("objects",[]) + r.get("materials",[]) + r.get("colors",[])
                    if r.get("style"): tags.append(r["style"])
                    if r.get("caption"): tags.append(r["caption"][:50])
                    ann.model_tags[self._vision._loaded or "Vision"] = list(set(tags))[:10]
                except Exception:
                    pass  # Model unavailable, non-critical
            # KnowledgeBridge
            try:
                from core.classifier import classify
                all_tags = []
                for t in ann.model_tags.values(): all_tags.extend(t)
                searchable = " ".join(all_tags) + " " + self._speech_text[:200]
                if searchable.strip():
                    r = classify(searchable)
                    if r["data"] and not r["data"][0]["unclassified"]:
                        ann.model_tags["KnowledgeBridge"] = [c["keyword"] for c in r["data"][0]["categories"]][:8]
            except Exception: pass  # Model unavailable — non-critical
            # 合并标签
            merged = set()
            for tags in ann.model_tags.values(): merged.update(tags)
            ann.user_tags = list(merged)[:15]
            # 回调UI
            if self.tag_ready_callback:
                self.tag_ready_callback(ann.frame_index, ann.model_tags, ann.user_tags)
            done[0] += 1
            self._report(f"识别 {done[0]}/{total}", 0.12 + 0.85 * (done[0]/total))
            return ann

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = [pool.submit(_recognize_one, ann) for ann in self._frames]
            for _ in as_completed(futs):
                if self._cancel:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break

        self._report(f"识别完成: {total}帧", 1.0)
        # 全部完成后入库
        for ann in self._frames:
            self._db.save_frame(self._video_path, self._video_name, ann)
        return total

    def run_models(self):
        """兼容旧接口 — 同步串行识别"""
        if not self._vision: self.init_models()
        total = len(self._frames)
        for i, ann in enumerate(self._frames):
            if self._cancel: break
            self._report(f"识别 {i+1}/{total}", 0.12 + 0.85*((i+1)/max(total,1)))
            self._recognize_single(ann)
        for ann in self._frames:
            self._db.save_frame(self._video_path, self._video_name, ann)
        return total

    def _recognize_single(self, ann: FrameAnnotation):
        """单帧识别 — run_models() 用"""
        if self._vision and self._vision.available:
            try:
                r = self._vision.analyze(ann.frame_path)
                tags = r.get("objects",[]) + r.get("materials",[]) + r.get("colors",[])
                if r.get("style"): tags.append(r["style"])
                ann.model_tags[self._vision._loaded or "Vision"] = list(set(tags))[:10]
            except Exception: pass  # Model unavailable — non-critical
        try:
            from core.classifier import classify
            all_t = []
            for v in ann.model_tags.values():
                all_t.extend(v)
            s = " ".join(all_t) + " " + self._speech_text[:200]
            if s.strip():
                r = classify(s)
                if r["data"] and not r["data"][0]["unclassified"]:
                    ann.model_tags["KnowledgeBridge"] = [c["keyword"] for c in r["data"][0]["categories"]][:8]
        except Exception: pass  # Model unavailable — non-critical
        merged = set()
        for v in ann.model_tags.values():
            merged.update(v)
        ann.user_tags = list(merged)[:15]

    # ═══════════════════════════════════════
    # 反馈 & 清理
    # ═══════════════════════════════════════
    def save_feedback(self):
        count = 0
        for ann in self._frames:
            if ann.edited:
                orig = set()
                for v in ann.model_tags.values():
                    orig.update(v)
                self._db.save_feedback(self._video_path, ",".join(sorted(orig)[:10]), ",".join(ann.user_tags), ann.score, ann.score_note)
                for tag in ann.user_tags: self._db.update_learning(tag, True)
                count += 1
        return count

    def cleanup(self):
        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _get_duration(self, path):
        from core.frame_extractor import get_video_duration
        return get_video_duration(path)

    @staticmethod
    def _fmt_ts(sec):
        h,m = divmod(int(sec),3600); m,s = divmod(m,60); ms = int((sec%1)*100)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:02d}"
