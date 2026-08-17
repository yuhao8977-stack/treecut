#!/usr/bin/env python3
"""
树剪 — 知识接收器
直接运行此脚本，粘贴词汇数据，自动学习并植入所有子系统。

用法:
  python receive.py                    # 交互式输入
  python receive.py --file data.json  # 从JSON文件批量导入

数据格式 (JSON):
{
  "copywriting": {
    "hooks": ["钩子句式1", "钩子句式2", ...],
    "selling_phrases": ["卖点描述句1", ...],
    "cta_templates": ["结尾引导语1", ...],
    "industry_terms": ["行业术语1", ...],
    "tone_words": ["语气词1", ...]
  },
  "protected_words": {
    "product_names": ["产品名称1", ...],
    "material_terms": ["材质复合词1", ...],
    "craft_terms": ["工艺复合词1", ...],
    "style_terms": ["风格复合词1", ...],
    "brand_terms": ["品牌专有词1", ...]
  },
  "knowledge_base": {
    "stone_variants": ["潘多拉", "宝格丽", ...],
    "craft_techniques": ["海棠角", "水磨边", ...],
    "hardware_items": ["公牛轨道插座", ...],
    "style_variants": ["意式中古风", ...],
    "color_names": ["奶油白", "哑光黑", ...]
  },
  "keyword_mapping": {
    "烤箱": ["内嵌烤箱"],
    "悬浮": ["悬浮式", "悬浮岛台"]
  },
  "synonyms": {
    "潘多拉岩板": ["潘多拉", "pandora", "潘多拉系列"]
  }
}
"""
import sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    p = argparse.ArgumentParser(description="树剪 知识接收器")
    p.add_argument("--file", "-f", type=str, help="从JSON文件导入")
    p.add_argument("--summary", "-s", action="store_true", help="显示已学习摘要")
    args = p.parse_args()

    from core.learner import get_learner
    learner = get_learner()

    if args.summary:
        learner.print_summary()
        return

    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"文件不存在: {args.file}")
            return
        data = json.loads(filepath.read_text(encoding="utf-8"))
        learner.bulk_learn(data)
        learner.print_summary()
        return

    # 交互模式
    print("=" * 55)
    print("  树剪 TreeCut — 知识接收器")
    print("=" * 55)
    print()
    print("  请粘贴 JSON 格式的词汇数据，输入空行结束:")
    print("  格式参考: python receive.py --help")
    print()

    lines = []
    print("📥 请粘贴数据 (输入空行结束):")
    while True:
        try:
            line = input()
            if line.strip() == "":
                break
            lines.append(line)
        except EOFError:
            break

    if not lines:
        print("未收到数据。")
        return

    try:
        data = json.loads("\n".join(lines))
        learner.bulk_learn(data)
        print()
        learner.print_summary()
        print()
        print("✅ 全部知识已植入:")
        print("  → DeepSeek 文案系统提示词")
        print("  → TTS 保护词词库 (protected_words.json)")
        print("  → 行业知识库 (石材/工艺/五金/风格)")
        print("  → 关键词-文件夹映射")
        print("  → 同义词规范化映射")
    except json.JSONDecodeError as e:
        print(f"❌ JSON 格式错误: {e}")
        print("请检查数据格式。参考: python receive.py --help")


if __name__ == "__main__":
    main()
