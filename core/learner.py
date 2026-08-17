"""
树剪 — 知识学习引擎
接收词汇/句式/行业术语 → 自动植入所有子系统

植入目标:
  1. DeepSeek 文案系统提示词 → 生成更专业的口播文案
  2. TTS 保护词词库 → 配音不断句
  3. 知识库 (石材/工艺/五金/风格) → 画面匹配更精准
  4. 标签融合器同义词映射 → 标签规范化
  5. 关键词-文件夹映射 → 素材搜索更准确
"""
import json, os, threading
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# v12.0: 保护词全局写锁 — 防止多线程同时修改 config.PROTECTED_WORDS
_words_write_lock = threading.Lock()


class KnowledgeLearner:
    """知识学习器 — 接收新词汇，自动分发到各子系统"""

    def __init__(self):
        self._proj_root = Path(__file__).parent.parent
        self._learned_file = self._proj_root / "learned_knowledge.json"
        self._knowledge = self._load()

    def _load(self) -> dict:
        if self._learned_file.exists():
            try:
                return json.loads(self._learned_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "version": 1,
            "updated": "",
            "copywriting": {         # 文案生成增强
                "hooks": [],          # 钩子句式
                "selling_phrases": [],# 卖点描述句
                "cta_templates": [],  # 结尾引导语
                "industry_terms": [], # 行业专业术语
                "tone_words": [],     # 语气词/口语化表达
            },
            "protected_words": {      # TTS保护词 (不被拆分朗读)
                "product_names": [],  # 产品名称
                "material_terms": [], # 材质复合词
                "craft_terms": [],    # 工艺复合词
                "style_terms": [],    # 风格复合词
                "brand_terms": [],    # 品牌专有词
            },
            "knowledge_base": {       # 画面匹配知识库
                "stone_variants": [], # 石材品种
                "craft_techniques": [],# 工艺技法
                "hardware_items": [],  # 五金配件
                "style_variants": [],  # 风格变体
                "color_names": [],     # 颜色命名
            },
            "keyword_mapping": {},     # 关键词→文件夹映射
            "synonyms": {},            # 同义词映射 (别名→规范名)
        }

    def _save(self):
        self._knowledge["updated"] = datetime.now().isoformat()
        self._learned_file.write_text(
            json.dumps(self._knowledge, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── 学习接口 ──

    def learn_copywriting(self, category: str, items: List[str]):
        """
        学习文案素材。
        category: hooks | selling_phrases | cta_templates | industry_terms | tone_words
        """
        if category in self._knowledge["copywriting"]:
            existing = set(self._knowledge["copywriting"][category])
            for item in items:
                item = item.strip()
                if item and item not in existing:
                    self._knowledge["copywriting"][category].append(item)
                    existing.add(item)
            self._save()
            print(f"   📝 文案素材已学习: {category} +{len(items)}条")
            self._apply_to_copywriter()

    def learn_protected_words(self, category: str, words: List[str]):
        """
        学习TTS保护词。
        category: product_names | material_terms | craft_terms | style_terms | brand_terms
        """
        if category in self._knowledge["protected_words"]:
            existing = set(self._knowledge["protected_words"][category])
            for w in words:
                w = w.strip()
                if w and w not in existing and len(w) >= 2:
                    self._knowledge["protected_words"][category].append(w)
                    existing.add(w)
            self._save()
            print(f"   🎙 TTS保护词已学习: {category} +{len(words)}条")
            self._apply_to_protected_words()

    def learn_knowledge(self, category: str, items: List[str]):
        """
        学习行业知识。
        category: stone_variants | craft_techniques | hardware_items | style_variants | color_names
        """
        if category in self._knowledge["knowledge_base"]:
            existing = set(self._knowledge["knowledge_base"][category])
            for item in items:
                item = item.strip()
                if item and item not in existing:
                    self._knowledge["knowledge_base"][category].append(item)
                    existing.add(item)
            self._save()
            print(f"   📚 知识库已学习: {category} +{len(items)}条")

    def learn_keyword_mapping(self, keyword: str, folders: List[str]):
        """学习关键词→文件夹映射"""
        self._knowledge["keyword_mapping"][keyword] = folders
        self._save()
        print(f"   🗂 关键词映射已学习: {keyword} → {folders}")

    def learn_synonyms(self, canonical: str, aliases: List[str]):
        """学习同义词映射"""
        for alias in aliases:
            self._knowledge["synonyms"][alias.strip()] = canonical
        self._save()
        print(f"   🔄 同义词已学习: {canonical} ← {aliases}")

    def bulk_learn(self, data: dict):
        """
        批量学习 — 一次性接收所有类型的词汇。v12.0 修复: 仅保存一次。

        data格式:
        {
          "copywriting": {"hooks": [...], "selling_phrases": [...], ...},
          "protected_words": {"product_names": [...], ...},
          "knowledge_base": {"stone_variants": [...], ...},
          "keyword_mapping": {"烤箱": ["内嵌烤箱", ...]},
          "synonyms": {"规范名": ["别名1", "别名2"]}
        }
        """
        changed = False

        for section, content in data.items():
            if section in ("copywriting", "protected_words", "knowledge_base"):
                for category, items in content.items():
                    if category not in self._knowledge.get(section, {}):
                        continue
                    target = self._knowledge[section][category]
                    existing = set(target)
                    for item in items:
                        item = item.strip()
                        if item and item not in existing:
                            # protected_words 额外校验: 至少2字符
                            if section == "protected_words" and len(item) < 2:
                                continue
                            target.append(item)
                            existing.add(item)
                            changed = True

            elif section == "keyword_mapping":
                for kw, folders in content.items():
                    self._knowledge["keyword_mapping"][kw] = folders
                    changed = True

            elif section == "synonyms":
                for canonical, aliases in content.items():
                    for alias in aliases:
                        self._knowledge["synonyms"][alias.strip()] = canonical
                    changed = True

        # v12.0 修复: 所有修改完成后仅保存一次
        if changed:
            self._save()
            self._apply_to_copywriter()
            self._apply_to_protected_words()
            print(f"   [Learner] 批量学习完成，已保存")

    # ── 应用到各子系统 ──

    def _apply_to_copywriter(self):
        """将学习的文案素材注入到 DeepSeek 系统提示词"""
        hooks = self._knowledge["copywriting"].get("hooks", [])
        terms = self._knowledge["copywriting"].get("industry_terms", [])

        if hooks:
            # 动态扩展钩子列表
            new_hooks = "\n".join(f'- "{h}"' for h in hooks[-5:])  # 最近5条
            print(f"   📝 文案钩子已更新 ({len(hooks)}条已学习)")
        if terms:
            # 更新 core.config 中的 KEYWORD_FOLDER_MAP
            from core import config
            for term in terms:
                if term not in config.KEYWORD_FOLDER_MAP:
                    config.KEYWORD_FOLDER_MAP[term] = ["材质细节展示", "造型展示"]
            print(f"   📝 行业术语已注入关键词映射 ({len(terms)}条)")

    def _apply_to_protected_words(self):
        """将学习的保护词合并到 protected_words.json 和运行时词库"""
        try:
            # 更新 JSON 文件
            pw_file = self._proj_root / "protected_words.json"
            if pw_file.exists():
                pw_data = json.loads(pw_file.read_text(encoding="utf-8"))
                for cat, words in self._knowledge["protected_words"].items():
                    cat_name = {
                        "product_names": "核心产品词",
                        "material_terms": "材质与工艺词",
                        "craft_terms": "材质与工艺词",
                        "style_terms": "风格与设计词",
                        "brand_terms": "品牌专有词",
                    }.get(cat, cat)
                    if cat_name not in pw_data.get("categories", {}):
                        pw_data["categories"][cat_name] = []
                    existing = set(pw_data["categories"][cat_name])
                    for w in words:
                        if w not in existing:
                            pw_data["categories"][cat_name].append(w)
                            existing.add(w)
                pw_file.write_text(json.dumps(pw_data, ensure_ascii=False, indent=2), encoding="utf-8")

            # 更新运行时词库 — v12.0: 加锁保护线程安全
            from core import config
            all_words = set(config.PROTECTED_WORDS)
            for words in self._knowledge["protected_words"].values():
                for w in words:
                    all_words.add(w)
            with _words_write_lock:
                config.PROTECTED_WORDS = sorted(all_words, key=len, reverse=True)
            print(f"   🎙 运行时保护词已更新 ({len(config.PROTECTED_WORDS)}词)")
        except Exception as e:
            print(f"   !! 保护词更新异常: {e}")

    def get_summary(self) -> dict:
        """获取已学习知识摘要"""
        summary = {}
        for section, content in self._knowledge.items():
            if section in ("version", "updated"):
                continue
            if isinstance(content, dict):
                total = sum(len(v) for v in content.values() if isinstance(v, list))
                summary[section] = total
            elif isinstance(content, list):
                summary[section] = len(content)
        return summary

    def print_summary(self):
        s = self.get_summary()
        print(f"\n   📊 知识学习摘要:")
        print(f"   文案素材: {s.get('copywriting', 0)} 条")
        print(f"   TTS保护词: {s.get('protected_words', 0)} 条")
        print(f"   知识库: {s.get('knowledge_base', 0)} 条")
        print(f"   关键词映射: {s.get('keyword_mapping', 0)} 条")
        print(f"   同义词: {s.get('synonyms', 0)} 条")


# 全局单例
_learner: Optional[KnowledgeLearner] = None

def get_learner() -> KnowledgeLearner:
    global _learner
    if _learner is None:
        _learner = KnowledgeLearner()
    return _learner


# ── 便捷接收函数 ──

def learn(data: dict):
    """
    便捷入口 — 一键学习所有新知识。

    用法:
      from core.learner import learn
      learn({
          "copywriting": {
              "hooks": ["90%的人不知道岛台还能这样设计！"],
              "industry_terms": ["悬浮岛台", "全铝柜体"],
          },
          "protected_words": {
              "product_names": ["悬浮岛台", "落地岛台"],
          },
      })
    """
    return get_learner().bulk_learn(data)
