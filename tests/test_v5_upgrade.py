"""V3.5 升级验证测试"""
import sys, os, json, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestVisionManager(unittest.TestCase):
    def test_load_models(self):
        from core.vision_unified import VisionModel
        v = VisionModel()
        available = v.available
        print(f"VisionModel available: {available}")
        self.assertTrue(available, "VisionModel should be available (Ollama or local)")

    def test_config_toggle(self):
        import os
        model_name = os.environ.get("TREECUT_VISION_MODEL", "qwen2.5-ollama")
        self.assertIn(model_name, ["qwen2.5-ollama", "qwen3-3b", "qwen3-7b", "florence2", "kimi-vl"])


class TestAutoLabeler(unittest.TestCase):
    def test_schema_init(self):
        from core.frame_annotator import AnnotDB
        db = AnnotDB()
        stats = db.get_stats()
        self.assertIn("total_frames", stats)
        print(f"AnnotDB stats: {stats}")

    def test_quick_analyze(self):
        """快速测试: 验证流程不崩溃"""
        from core.frame_annotator import FrameAnnotator
        annotator = FrameAnnotator()
        # 找一个测试视频
        test_video = None
        import subprocess, tempfile
        for root, dirs, files in os.walk(r"Z:\已处理素材"):
            for f in files:
                if f.endswith(".mp4"):
                    test_video = os.path.join(root, f)
                    if os.path.getsize(test_video) < 50*1024*1024:  # <50MB
                        break
            if test_video: break

        if not test_video:
            self.skipTest("No test video found")
            return

        t0 = time.time()
        n = annotator.extract_frames(test_video, interval=2.0, max_frames=5)
        elapsed = time.time() - t0
        print(f"Extracted {n} frames in {elapsed:.1f}s")
        self.assertGreaterEqual(n, 0)
        # Clean up
        annotator.cleanup()


class TestSmartMatcher(unittest.TestCase):
    def test_search(self):
        from material_engine_v3.core.smart_matcher import SmartMatcher
        matcher = SmartMatcher()
        results = matcher.search("岩板台面 潘多拉", top_k=5)
        print(f"Search found: {len(results)} results")
        if results:
            self.assertIn("video_path", results[0])
            self.assertIn("match_method", results[0])

    def test_search_by_copy(self):
        from material_engine_v3.core.smart_matcher import SmartMatcher
        matcher = SmartMatcher()
        clips = matcher.search_by_copy("岩板台面潘多拉哑光, 意式中古风岛台", num_clips=3)
        print(f"Copy match: {len(clips)} clips")
        self.assertLessEqual(len(clips), 3)


class TestPipelineIntegration(unittest.TestCase):
    def test_ai_match_clips(self):
        from core.pipeline import ai_match_clips
        clips = ai_match_clips("奶油风伸缩岩板岛台", num_clips=4)
        print(f"Pipeline match: {len(clips)} clips")
        # 即使无AI库, 也应返回空列表而非崩溃
        self.assertIsInstance(clips, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
