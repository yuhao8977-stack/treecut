"""测试本地模型加载和推理"""
import sys, os, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

class TestModelDownloader(unittest.TestCase):
    def test_list_models(self):
        from utils.model_downloader import list_available, ensure_model_available, MODEL_HF
        self.assertGreater(len(MODEL_HF), 3)
        ok = ensure_model_available("qwen2.5-ollama")
        print(f"Default model available: {ok}")

class TestVisionV2(unittest.TestCase):
    def test_default_model(self):
        from core.vision_unified import VisionModel
        v = VisionModel()
        self.assertTrue(v.available)
        print(f"Model: {v.model_name}, available={v.available}")

    def test_inference(self):
        from core.vision_unified import VisionModel
        v = VisionModel()
        if not v.available: self.skipTest("No model available")
        # Find a test image
        img = None
        for root, dirs, files in os.walk(r"Z:\已处理素材"):
            for f in files:
                if f.endswith(".mp4"):
                    import subprocess, tempfile
                    vp = os.path.join(root, f)
                    tmp = tempfile.mktemp(suffix=".jpg")
                    subprocess.run(["ffmpeg","-y","-i",vp,"-vframes","1","-q:v","2",tmp],capture_output=True,timeout=10)
                    if os.path.exists(tmp): img = tmp; break
            if img: break
        if not img: self.skipTest("No image"); return
        t0 = time.time()
        result = v.analyze(img)
        elapsed = time.time() - t0
        print(f"Inference: {len(result)} keys in {elapsed:.1f}s")
        os.remove(img)

if __name__ == "__main__":
    unittest.main(verbosity=2)
