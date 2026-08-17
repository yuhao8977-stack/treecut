"""
╔══════════════════════════════════════════════════════════════╗
║  📦 video_editor.draft_builder — 剪映草稿JSON生成         ║
╚══════════════════════════════════════════════════════════════╝
"""
import uuid
import time
import re
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from core.config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, FPS, VIDEO_VOLUME, BGM_VOLUME, BGM_FADE_IN, BGM_FADE_OUT,
    TTS_VOLUME, SUBTITLE_FONT_SIZE, SUBTITLE_STROKE_WIDTH,
    SUBTITLE_BACKGROUND_ENABLED, SUBTITLE_POSITION_Y,
    JIANGYING_DRAFT_DIR, OUTPUT_DRAFT_DIR, MAX_DURATION_ERROR,
)

# pyJianYingDraft — 可选的第三方库
try:
    from pyJianYingDraft.script_file import ScriptFile
    from pyJianYingDraft.track import TrackType
    from pyJianYingDraft.local_materials import VideoMaterial, AudioMaterial
    from pyJianYingDraft.video_segment import VideoSegment
    from pyJianYingDraft.audio_segment import AudioSegment
    from pyJianYingDraft.text_segment import TextSegment, TextStyle, TextBorder, TextShadow, TextBackground
    from pyJianYingDraft.time_util import Timerange
    from pyJianYingDraft.segment import ClipSettings
    from pyJianYingDraft.local_materials import CropSettings
    _HAS_PYDRAFT = True
except ImportError:
    _HAS_PYDRAFT = False


def sec_to_us(seconds: float) -> int:
    return int(seconds * 1_000_000)


class JianyingDraftBuilder:
    """构建剪映专业版草稿文件"""

    def __init__(self, draft_name: str, keyword: str):
        if not _HAS_PYDRAFT:
            raise ImportError("pyJianYingDraft 库未安装,无法生成草稿")

        self.draft_name = draft_name
        self.keyword = keyword
        self.draft_id = uuid.uuid4().hex

        self.script = ScriptFile(width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fps=FPS, maintrack_adsorb=True)
        self.script.content["name"] = draft_name
        self.script.content["id"] = self.draft_id

        self.script.add_track(TrackType.video, "video")
        self.script.add_track(TrackType.audio, "BGM")
        self.script.add_track(TrackType.audio, "配音", relative_index=1)
        self.script.add_track(TrackType.text, "text", relative_index=999)

        self._current_time_us = 0
        self._total_duration_us = 0
        self._has_tts = False

    def add_video_clip(self, file_path: Path, source_start: float,
                       clip_duration: float, speed: float = 1.0):
        source_start_us = sec_to_us(source_start)
        source_duration_us = sec_to_us(clip_duration)

        CROP_BOTTOM_RATIO = 0.18
        crop = CropSettings(lower_left_y=1.0 - CROP_BOTTOM_RATIO, lower_right_y=1.0 - CROP_BOTTOM_RATIO)
        fill_scale = 1.0 / (1.0 - CROP_BOTTOM_RATIO)
        clip_cfg = ClipSettings(scale_x=fill_scale, scale_y=fill_scale)

        material = VideoMaterial(str(file_path.absolute()), crop_settings=crop)
        actual_duration = material.duration
        if source_start_us >= actual_duration:
            source_start_us = 0
        if source_start_us + source_duration_us > actual_duration:
            if actual_duration >= source_duration_us:
                source_start_us = max(0, actual_duration - source_duration_us)
            else:
                source_start_us = 0
                source_duration_us = actual_duration

        target_trange = Timerange(self._current_time_us, source_duration_us)
        source_trange = Timerange(source_start_us, source_duration_us)

        segment = VideoSegment(material=material, target_timerange=target_trange,
                               source_timerange=source_trange, speed=speed,
                               volume=VIDEO_VOLUME, clip_settings=clip_cfg)
        self.script.add_segment(segment, "video")
        self._current_time_us += segment.target_timerange.duration
        self._total_duration_us = max(self._total_duration_us, self._current_time_us)

    def add_audio_bgm(self, file_path: Path, climax_start_sec: float = None):
        material = AudioMaterial(str(file_path.absolute()))
        bgm_duration_us = self._total_duration_us
        target_trange = Timerange(0, bgm_duration_us)
        source_duration = min(bgm_duration_us, material.duration)
        source_start_us = 0
        if climax_start_sec and climax_start_sec > 0:
            source_start_us = int(climax_start_sec * 1_000_000)
            if source_start_us + source_duration > material.duration:
                source_start_us = max(0, material.duration - source_duration)
        source_trange = Timerange(source_start_us, source_duration)
        segment = AudioSegment(material=material, target_timerange=target_trange,
                               source_timerange=source_trange, speed=1.0, volume=BGM_VOLUME)
        segment.add_fade(int(BGM_FADE_IN * 1_000_000), int(BGM_FADE_OUT * 1_000_000))
        self.script.add_segment(segment, "BGM")

    def add_tts_audio(self, file_path: Path):
        material = AudioMaterial(str(file_path.absolute()))
        max_tts_us = self._total_duration_us
        actual_tts_us = min(material.duration, max_tts_us)
        target_trange = Timerange(0, actual_tts_us)
        source_trange = Timerange(0, actual_tts_us)
        segment = AudioSegment(material=material, target_timerange=target_trange,
                               source_timerange=source_trange, speed=1.0, volume=TTS_VOLUME)
        self.script.add_segment(segment, "配音")
        self._has_tts = True

    def trim_all_to_tts(self, tts_duration_sec: float):
        target_us = int(tts_duration_sec * 1_000_000)
        original_us = self._total_duration_us
        if original_us <= target_us + int(MAX_DURATION_ERROR * 1_000_000):
            return
        trim_needed = original_us - target_us
        video_track = self.script.tracks.get("video")
        if video_track and video_track.segments:
            segs = video_track.segments
            while trim_needed > 0 and segs:
                last = segs[-1]
                if last.target_timerange.duration > trim_needed:
                    last.target_timerange.duration -= trim_needed
                    trim_needed = 0
                else:
                    trim_needed -= last.target_timerange.duration
                    segs.pop()
        self._total_duration_us = target_us
        self._current_time_us = target_us

    def add_subtitle(self, text: str, start_time_us: int, duration_us: int):
        target_trange = Timerange(start_time_us, duration_us)
        style = TextStyle(size=SUBTITLE_FONT_SIZE, align=1, auto_wrapping=True,
                          color=(1.0, 0.97, 0.90), alpha=1.0)
        border = TextBorder(alpha=0.9, color=(0.0, 0.0, 0.0), width=SUBTITLE_STROKE_WIDTH)
        shadow = TextShadow(alpha=0.35, color=(0.0, 0.0, 0.0), diffuse=10.0, distance=3.5, angle=-45.0)
        clip = ClipSettings(transform_y=SUBTITLE_POSITION_Y)
        background = None
        if SUBTITLE_BACKGROUND_ENABLED:
            background = TextBackground(color="#000000", style=1, alpha=0.35, round_radius=0.15,
                                        height=0.12, width=0.15, horizontal_offset=0.5, vertical_offset=0.5)
        segment = TextSegment(text=text, timerange=target_trange, style=style,
                              clip_settings=clip, border=border, shadow=shadow, background=background)
        self.script.add_segment(segment, "text")

    def build_draft_content(self) -> dict:
        self.script.duration = self._total_duration_us
        return json.loads(self.script.dumps())

    def build_draft_meta_info(self) -> dict:
        now_ts = int(time.time() * 1000)
        return {
            "draft_id": self.draft_id.upper(),
            "draft_name": self.draft_name,
            "draft_root_path": JIANGYING_DRAFT_DIR.replace("\\", "/"),
            "tm_duration": self._total_duration_us,
            "draft_cloud_package_completed_time": "",
            "draft_cloud_last_action_download": False,
            "draft_cloud_materials": [],
            "draft_enterprise_info": {"draft_enterprise_extra": "", "draft_enterprise_id": "", "draft_enterprise_name": "", "enterprise_material": []},
            "draft_fold_path": "",
            "draft_is_ai_packaging_used": False,
            "draft_is_ai_shorts": False,
            "draft_is_ai_translate": False,
            "draft_is_article_video_draft": False,
            "draft_is_from_deeplink": False,  # v12.0 修复: 字符串→布尔值
            "draft_is_invisible": False,
            "draft_materials": [{"type": 0, "value": []}, {"type": 1, "value": []}, {"type": 2, "value": []},
                               {"type": 3, "value": []}, {"type": 6, "value": []}, {"type": 7, "value": []}, {"type": 8, "value": []}],
            "draft_new_version": "",
            "draft_removable_storage_device": "",
            "draft_segment_extra_info": [],
            "draft_type": "",
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_modified": 0,
            "tm_draft_removed": 0,
        }


def save_draft(builder: JianyingDraftBuilder, keyword: str,
               video_log_id: int = None) -> Path:
    """保存草稿到剪映草稿目录"""
    draft_content = builder.build_draft_content()
    draft_meta = builder.build_draft_meta_info()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw = re.sub(r'[^\w一-鿿]', '', keyword)[:10]
    draft_folder_name = f"{timestamp}_{safe_kw}_树剪"

    draft_dir = Path(JIANGYING_DRAFT_DIR) / draft_folder_name
    draft_dir.mkdir(parents=True, exist_ok=True)

    content_path = draft_dir / "draft_content.json"
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(draft_content, f, ensure_ascii=False, indent=4)

    meta_path = draft_dir / "draft_meta_info.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(draft_meta, f, ensure_ascii=False, indent=None)

    settings_path = draft_dir / "draft_settings"
    now_ts = int(time.time())
    settings_content = (
        f"[General]\ndraft_create_time={now_ts}\ndraft_last_edit_time={now_ts}\n"
        f"real_edit_seconds=0\nreal_edit_keys=0\n"
    )
    with open(settings_path, "w", encoding="utf-8") as f:
        f.write(settings_content)

    print(f"\n   ✅ 剪映草稿已生成！")
    print(f"   📂 草稿目录: {draft_dir}")

    # 备份
    backup_dir = Path(OUTPUT_DRAFT_DIR) / draft_folder_name
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(content_path, backup_dir / "draft_content.json")
    shutil.copy2(meta_path, backup_dir / "draft_meta_info.json")
    print(f"   💾 备份已保存: {backup_dir}")

    return draft_dir
