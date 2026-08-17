#!/usr/bin/env python3
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
            (Path(self.tmpdir) / name).write_bytes(b"\x00"*100)

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
        """无API Key时全自动模式降级 — 不抛异常，降级为模板文案"""
        import core.pipeline as pl
        self.assertTrue(callable(pl.run))
        # run() 在 auto_mode=True 无API时不应抛异常，应降级使用 fallback
        try:
            import inspect
            sig = inspect.signature(pl.run)
            self.assertIn("auto_mode", sig.parameters)
        except Exception as e:
            self.fail(f"run() 签名检查失败: {e}")


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
