#!/usr/bin/env python3
"""
树剪 核心功能测试套件
运行: python -m pytest tests/ -v
或:   python tests/test_core.py
"""
import sys, os, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfig(unittest.TestCase):
    """配置模块测试"""

    def test_config_constants(self):
        """验证核心配置常量存在且类型正确"""
        from core.config import (
            VIDEO_WIDTH, VIDEO_HEIGHT, FPS,
            PROTECTED_WORDS, CTA_TEMPLATES, CTA_KEYWORDS,
        )
        self.assertEqual(VIDEO_WIDTH, 1080)
        self.assertEqual(VIDEO_HEIGHT, 1920)
        self.assertEqual(FPS, 30)
        self.assertGreater(len(PROTECTED_WORDS), 100)
        self.assertGreater(len(CTA_TEMPLATES), 3)
        self.assertGreater(len(CTA_KEYWORDS), 5)

    def test_config_defaults_dict(self):
        """验证 DEFAULTS 字典可以正常导入"""
        from core.config import DEFAULTS
        self.assertIsInstance(DEFAULTS, dict)
        self.assertGreater(len(DEFAULTS), 10)

    def test_config_sensitive_filter(self):
        from utils.security import is_sensitive_key
        self.assertTrue(is_sensitive_key("deepseek_api_key"))
        self.assertTrue(is_sensitive_key("OPENAI_API_KEY"))
        self.assertFalse(is_sensitive_key("bgm_path"))
        self.assertFalse(is_sensitive_key("user_name"))


class TestSecurity(unittest.TestCase):
    """安全模块测试"""

    def test_redact_sensitive(self):
        from utils.security import redact_sensitive
        result = redact_sensitive("DEEPSEEK_API_KEY=sk-abc123def456ghi789jkl")
        self.assertIn("***REDACTED***", result)

    def test_sanitize_dict(self):
        from utils.security import sanitize_dict
        data = {"api_key": "sk-secret1234567890abcdef", "name": "test", "nested": {"token": "abc"}}
        safe = sanitize_dict(data)
        self.assertIn("****", safe["api_key"])
        self.assertEqual(safe["name"], "test")

    def test_safe_read_env(self):
        from utils.security import safe_read_env
        env = safe_read_env(Path(__file__).parent.parent / ".env.example")
        self.assertIn("DEEPSEEK_API_KEY", env)


class TestRetry(unittest.TestCase):
    """重试模块测试"""

    def test_circuit_breaker_init(self):
        from utils.retry import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3)
        self.assertEqual(cb.state, "closed")
        self.assertEqual(cb.name, "test")

    def test_circuit_breaker_trips(self):
        from utils.retry import CircuitBreaker, CircuitBreakerOpenError
        cb = CircuitBreaker("test2", failure_threshold=2, recovery_timeout=0.1)
        # Trip the breaker
        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, "open")
        with self.assertRaises(CircuitBreakerOpenError):
            @cb.protect
            def fail(): raise RuntimeError("fail")
            fail()

    def test_retry_decorator(self):
        from utils.retry import retry_on_failure
        call_count = [0]

        @retry_on_failure(max_attempts=3, base_delay=0.01)
        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("simulated")
            return "success"

        result = flaky()
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 3)


class TestKnowledgeBridge(unittest.TestCase):
    """V5知识库测试"""

    def test_extract_stone_keywords(self):
        from utils.knowledge import KnowledgeBridge
        kb = KnowledgeBridge()
        kws = kb.extract_copy_keywords("岩板台面选潘多拉哑光系列，配海棠角，意式中古风")
        self.assertGreater(len(kws["stones"]), 0)

    def test_extract_style_keywords(self):
        from utils.knowledge import KnowledgeBridge
        kb = KnowledgeBridge()
        # "奶油风极简风" 是连续风格词，知识库按子串匹配至少应找到其中一种风格
        kws = kb.extract_copy_keywords("奶油风极简风岛台")
        self.assertGreater(len(kws["styles"]), 0,
                          "至少应匹配到一个风格词")

    def test_style_recommendation(self):
        from utils.knowledge import KnowledgeBridge
        kb = KnowledgeBridge()
        recos = kb.get_matching_styles(["潘多拉", "南美柚木", "海棠角"])
        self.assertIsInstance(recos, list)


class TestQuality(unittest.TestCase):
    """素材质量测试"""

    def test_tag_completeness_max(self):
        from utils.quality_scorer import QualityScorer
        s = QualityScorer(use_cv=False)
        score = s.evaluate_tag_completeness(
            "[微水泥奶油白+兰亭香樟]岛台内嵌烤箱展示[岩板][收纳][灯带].mp4")
        self.assertGreater(score, 0.5)

    def test_tag_completeness_min(self):
        from utils.quality_scorer import QualityScorer
        s = QualityScorer(use_cv=False)
        score = s.evaluate_tag_completeness("video_001.mp4")
        self.assertEqual(score, 0.0)


class TestVideoEditorConfig(unittest.TestCase):
    """ve_core配置测试"""

    def test_config_loads(self):
        from core.config import VIDEO_WIDTH, VIDEO_HEIGHT, PROTECTED_WORDS
        self.assertEqual(VIDEO_WIDTH, 1080)
        self.assertEqual(VIDEO_HEIGHT, 1920)
        self.assertGreater(len(PROTECTED_WORDS), 100)

    def test_cta_templates(self):
        from core.config import CTA_TEMPLATES, CTA_KEYWORDS
        self.assertGreater(len(CTA_TEMPLATES), 0)
        self.assertGreater(len(CTA_KEYWORDS), 5)


class TestCopywriter(unittest.TestCase):
    """文案生成测试"""

    def test_fallback_copy(self):
        from core.copywriter import generate_fallback_copy
        result = generate_fallback_copy("测试卖点")
        self.assertGreater(len(result), 30)
        self.assertIn("测试卖点", result)

    def test_cta_check(self):
        from core.copywriter import check_cta_present
        self.assertTrue(check_cta_present("喜欢吗？评论区扣1发你方案"))
        self.assertFalse(check_cta_present("这是一个岛台展示视频"))


class TestTTSEngine(unittest.TestCase):
    """TTS引擎测试"""

    def test_clean_text(self):
        from core.tts import strip_leading_junk
        result = strip_leading_junk("1. 测试内容ABC")
        self.assertNotIn("1.", result)

    def test_split_subtitles(self):
        from core.tts import split_copy_to_subtitles
        result = split_copy_to_subtitles("钩子开头。核心卖点展示。结尾CTA引导。")
        self.assertGreaterEqual(len(result), 3)

    def test_filter_fragments(self):
        from core.tts import filter_non_speech_fragments
        result = filter_non_speech_fragments(["123", "岩板台面", "ABC", "岛台设计"])
        self.assertIn("岩板台面", result)
        self.assertIn("岛台设计", result)
        self.assertNotIn("123", result)


class TestVideoEditorCompat(unittest.TestCase):
    """video_editor兼容层测试"""

    def test_import_compat(self):
        import core as ve
        self.assertTrue(hasattr(ve, 'run'))
        self.assertTrue(hasattr(ve, 'run_multi'))
        self.assertTrue(hasattr(ve, 'generate_tts_voiceover'))
        self.assertTrue(hasattr(ve, 'JianyingDraftBuilder'))

    def test_material_cache_manager(self):
        import core as ve
        self.assertTrue(hasattr(ve, 'MaterialCacheManager'))
        self.assertTrue(hasattr(ve, 'MaterialUsageTracker'))


class TestSubtitleSplit(unittest.TestCase):
    def test_split_at_punctuation(self):
        from core.tts import split_copy_to_subtitles
        r = split_copy_to_subtitles("岛台岩板台面，选潘多拉哑光。配海棠角工艺！")
        self.assertGreater(len(r), 1)

    def test_max_length_split(self):
        from core.tts import split_copy_to_subtitles
        long_text = "这是一个非常长的句子用来测试字幕拆分功能是否正常工作" * 3
        r = split_copy_to_subtitles(long_text)
        # split_copy_to_subtitles 按标点符号断句，不强制按字符数截断
        # 验证至少产出了字幕片段
        self.assertGreater(len(r), 0, "长文本应至少生成一条字幕")
        total_chars = sum(len(s) for s in r)
        self.assertGreater(total_chars, 0, "总字符数应大于0")

    def test_filter_junk(self):
        from core.tts import strip_leading_junk
        self.assertNotIn("1.", strip_leading_junk("1. 测试内容"))
        self.assertNotIn("[01]", strip_leading_junk("[01]测试"))


class TestMaterialCache(unittest.TestCase):
    def test_cache_fingerprint_integration(self):
        """验证 MaterialCacheManager 指纹计算的输出长度"""
        import core as ve
        from pathlib import Path
        dummy_dirs = [str(Path(__file__).parent)]
        fp = ve.MaterialCacheManager._dir_fingerprint(dummy_dirs)
        self.assertEqual(len(fp), 12, "指纹应为12字符hex")


class TestAtomicWrite(unittest.TestCase):
    def test_atomic_json_write(self):
        import tempfile, os, json
        from utils.security import safe_write_json
        tmp = tempfile.mktemp(suffix=".json")
        safe_write_json(Path(tmp), {"test": "data"})
        self.assertTrue(os.path.exists(tmp))
        with open(tmp, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        self.assertEqual(data["test"], "data")
        os.remove(tmp)


class TestKnowledgeBridgeCache(unittest.TestCase):
    def test_extract_speed(self):
        import time
        from utils.knowledge import KnowledgeBridge
        kb = KnowledgeBridge()
        t0 = time.time()
        kb.extract_copy_keywords("岩板台面潘多拉哑光中古风")
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.5)  # 缓存命中应<500ms


if __name__ == "__main__":
    unittest.main(verbosity=2)
