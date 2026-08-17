#!/usr/bin/env python3
"""
树剪 - 随机5脚本批量生成
从脚本库随机选取5个脚本，生成5条视频
"""
import sys, os, io, random, time, gc, traceback

# 确保编码正确
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 设置项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(PROJECT_ROOT) / "ai_material_library.db"


def pick_random_scripts(n=5):
    """从脚本库随机选取n个有效脚本"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, content, tags FROM learned_scripts "
        "WHERE content IS NOT NULL AND length(content) > 20"
    )
    rows = cursor.fetchall()
    conn.close()

    # 过滤掉Excel垃圾数据
    valid = [
        (r[0], r[1].strip(), r[2])
        for r in rows
        if '_xlfn.' not in r[1]
        and 'DISPIMG' not in r[1]
        and len(r[1].strip()) >= 20
    ]
    print(f"[脚本库] 共 {len(valid)} 个有效脚本, 随机选取 {n} 个\n")

    random.seed()
    samples = random.sample(valid, min(n, len(valid)))
    return samples


def extract_keyword(script_text):
    """从脚本文本中提取最可能的卖点关键词"""
    # 常见卖点关键词按优先级
    candidates = [
        "岛台", "岩板", "烤箱", "蒸箱", "烟机", "灶具", "洗碗机",
        "水槽", "龙头", "柜体", "台面", "酒柜", "冰箱", "咖啡机",
        "微水泥", "奶油风", "极简", "新中式", "法式", "意式", "中古",
        "奢石", "木纹", "洞石", "寒江雪", "黑武士", "胡桃木",
        "伸缩", "悬浮", "预制", "果冻砖", "马赛克", "镂空砖",
    ]
    for kw in candidates:
        if kw in script_text:
            return kw
    # 默认返回岛台（最常见的主题）
    return "岛台"


def record_script_usage(script_id, keyword, draft_dir, success):
    """记录脚本使用情况"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "UPDATE learned_scripts SET usage_count = usage_count + 1, "
            "last_used_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), script_id)
        )
        conn.execute(
            "INSERT INTO generation_log (script_id, keyword, draft_dir, score, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (script_id, keyword, draft_dir or "", 5 if success else 0,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"   [WARN] 使用记录失败: {e}")


def main():
    print("=" * 60)
    print("  树剪 TreeCut - 随机5脚本批量生成")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 选取随机脚本
    scripts = pick_random_scripts(5)

    # 显示所选脚本
    for i, (sid, content, tags) in enumerate(scripts):
        kw = extract_keyword(content)
        print(f"  [{i+1}/5] ID={sid} | 关键词={kw}")
        print(f"        {content[:100]}...")
        print()

    # 2. 导入核心模块
    print("=" * 60)
    print("  加载核心模块...")
    from core.pipeline import run
    from core.script_learning import ScriptLibrary
    print("  [OK] 核心模块加载完成\n")

    # 3. 逐个生成
    results = []
    for i, (script_id, content, tags) in enumerate(scripts):
        keyword = extract_keyword(content)

        print("=" * 60)
        print(f"  [{i+1}/5] 开始生成视频")
        print(f"  脚本ID: {script_id}")
        print(f"  关键词: {keyword}")
        print(f"  脚本长度: {len(content)} 字")
        print("=" * 60)

        t0 = time.time()
        result = None
        draft_dir = None

        try:
            result = run(
                keyword=keyword,
                copy_text_override=content,
                generate_tts=True,
                auto_bgm=True,
                script_id=script_id,
            )

            if result and "draft_dir" in result:
                draft_dir = result.get("draft_dir", "")
                elapsed = time.time() - t0
                print(f"\n  ✅ [{i+1}/5] 生成成功! ({elapsed:.0f}秒)")
                print(f"  输出目录: {draft_dir}")
                record_script_usage(script_id, keyword, draft_dir, True)
                results.append({"index": i+1, "status": "success", "draft_dir": draft_dir})
            else:
                elapsed = time.time() - t0
                print(f"\n  ⚠️ [{i+1}/5] 生成结果为空 ({elapsed:.0f}秒)")
                record_script_usage(script_id, keyword, "", False)
                results.append({"index": i+1, "status": "empty", "result": str(result)})

        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n  ❌ [{i+1}/5] 生成失败 ({elapsed:.0f}秒): {e}")
            traceback.print_exc()
            record_script_usage(script_id, keyword, "", False)
            results.append({"index": i+1, "status": "failed", "error": str(e)})

        # 资源回收
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        if i < 4:
            wait = 3
            print(f"\n  等待 {wait} 秒后继续...")
            time.sleep(wait)

    # 4. 总结
    print("\n" + "=" * 60)
    print("  批量生成完成!")
    print("=" * 60)
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"  成功: {success_count}/5")
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {status_icon} [{r['index']}/5] {r['status']}: {r.get('draft_dir', r.get('error', ''))}")

    return results


if __name__ == "__main__":
    main()
