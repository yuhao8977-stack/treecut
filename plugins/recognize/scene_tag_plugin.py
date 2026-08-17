"""场景内容自动打标签插件"""
import os
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from PIL import Image
from core.model_pool import model_pool
from core.database import execute_sql, query_sql
from utils.cache_manager import cache_manager
logger = get_logger("plugin.scene_tag")
TAGS = ["产品展示", "安装过程", "细节特写", "空镜场景", "人物出镜", "文字说明"]
def load_scene_model():
    import torch
    from transformers import AutoModel, AutoTokenizer
    model_path = "./data/models/internvl2-2b"
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"模型路径不存在: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        load_in_4bit=True,
        trust_remote_code=True,
        device_map="auto",
    ).eval()
    return {"tokenizer": tokenizer, "model": model}
class SceneTagPlugin(BasePlugin):
    name = "scene_tag"
    category = "recognize"
    description = "场景内容自动打标签"
    def run(self, material_id: int, video_path: str) -> dict:
        cache_key = f"scene_tags_{material_id}"
        cached = cache_manager.get(cache_key, "scene_tags")
        if cached:
            for sid, tag in cached:
                execute_sql("UPDATE scene_features SET scene_tag=? WHERE id=?", (tag, sid))
            return {"status": "cached", "count": len(cached)}
        try:
            model_data = model_pool.get_model("scene_llm", load_scene_model)
        except Exception as e:
            logger.warning(f"场景理解模型加载失败: {e}，跳过场景标签")
            return {"status": "failed", "error": str(e)}
        tokenizer = model_data["tokenizer"]
        model = model_data["model"]
        scenes = query_sql(
            "SELECT id, keyframe_path FROM scene_features WHERE material_id=? AND keyframe_path != ''",
            (material_id,)
        )
        if not scenes:
            logger.warning("未找到场景数据")
            return {"status": "skipped", "count": 0}
        results = []
        prompt = f"从以下标签中选择最匹配这张图片的1个标签：{'、'.join(TAGS)}，只输出标签名称，不要其他内容。"
        for row in scenes:
            sid = row[0]
            img_path = row[1]
            if not os.path.exists(img_path):
                execute_sql("UPDATE scene_features SET scene_tag='未分类' WHERE id=?", (sid,))
                results.append((sid, "未分类"))
                continue
            try:
                image = Image.open(img_path).convert("RGB")
                response = model.chat(tokenizer, image, prompt, history=[])
                tag = response.strip().replace("。", "").replace(" ", "").replace("\n", "")
                if tag not in TAGS:
                    tag = "其他场景"
                execute_sql("UPDATE scene_features SET scene_tag=? WHERE id=?", (tag, sid))
                results.append((sid, tag))
            except Exception as e:
                logger.debug(f"场景{sid}标签生成失败: {e}")
                execute_sql("UPDATE scene_features SET scene_tag='处理失败' WHERE id=?", (sid,))
                results.append((sid, "处理失败"))
        cache_manager.set(cache_key, "scene_tags", results)
        logger.info(f"场景打标完成，共{len(results)}个")
        return {"status": "success", "count": len(results)}
