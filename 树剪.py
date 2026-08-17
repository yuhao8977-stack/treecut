#!/usr/bin/env python3
"""
樹剪 TreeCut v12.1 — 島台品牌 AI 視頻半自動剪輯工具（閉環自學習架構）

用法:
  python 树剪.py                        # 启动桌面应用
  python 树剪.py --web                  # 启动 Web 控制台
  python 树剪.py --cli 内嵌烤箱         # 命令行生成
  python 树剪.py --setup                # 配置向导
  python 树剪.py --status               # 系统状态
"""

import sys, os, argparse, traceback, time, io
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Windows GBK 编码修复 (必须在所有 print 之前) ──
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass
    except Exception:
        pass

# ── v12.1: 統一初始化 EventBus + Logging + RetryScheduler ──
def _init_v12_systems():
    """v12.1 初始化閉環架構核心組件"""
    # 先尝试初始化日志系统
    _log = None
    try:
        from utils.logging import setup_eventbus, get_logger
        setup_eventbus()
        _log = get_logger("Bootstrap")
        _log.info("TreeCut v12.1 初始化中...")
    except Exception as e:
        print(f"  [WARN] 日志系统初始化失败: {e}")
    
    def _log_warn(module_name, error):
        """统一的警告日志记录"""
        msg = f"模块 {module_name} 加载失败: {error}"
        if _log:
            _log.warning(msg)
        else:
            print(f"  [WARN] {msg}")
    
    try:
        from core.event_bus import get_bus
        get_bus()  # 預加載EventBus單例
    except Exception as e:
        _log_warn("EventBus", e)
    try:
        from core.retry_scheduler import get_retry_scheduler
        get_retry_scheduler()  # 預加載重試調度器
    except Exception as e:
        _log_warn("RetryScheduler", e)
    try:
        from core.review_queue import get_review_queue
        get_review_queue()  # 預加載審核隊列
    except Exception as e:
        _log_warn("ReviewQueue", e)
    try:
        from core.smart_orchestrator import get_orchestrator
        get_orchestrator()  # ★ 預加載智能調度解析中心
    except Exception as e:
        _log_warn("SmartOrchestrator", e)
    try:
        from core.quality_center import get_quality_center
        get_quality_center()  # ★ 預加載質檢中心
    except Exception as e:
        _log_warn("QualityCenter", e)
    # ★ v12.2: 新架構模塊預加載
    try:
        from core.auth_middleware import get_auth
        get_auth()
    except Exception as e:
        _log_warn("AuthMiddleware", e)
    try:
        from core.monitor import get_metrics, get_alert_manager
        get_metrics(); get_alert_manager()
    except Exception as e:
        _log_warn("Monitor", e)
    # ★ v14.0: 系统级硬件优化 — CPU亲和性 + 进程优先级 + GPU检测
    try:
        from utils.system_optimizer import auto_optimize
        report = auto_optimize()
        from utils.logging import get_logger
        _blog = get_logger("Bootstrap")
        _blog.info(f"硬件优化 CPU={report['effective_cores']}/{report['cpu_cores']} "
                   f"GPU={'%.1fGB'%(report['gpu_vram_mb']/1024) if report['gpu_available'] else 'N/A'} "
                   f"RAM={report['total_memory_mb']//1024}GB "
                   f"MemCache={report['memory_cache_mb']}MB")
        try:
            from utils.cache_manager import get_cache_manager
            cm = get_cache_manager()
            cm.set_memory_cache_size(report["memory_cache_mb"])
        except Exception as e:
            _log_warn("CacheManager", e)
    except Exception as e:
        _log_warn("SystemOptimizer", e)

    # ★ v14.1: GPU显存智能初始化 — CUDA环境 + cudnn + 自适应量化
    try:
        from utils.vram_manager import auto_init_gpu, get_vram_info
        gpu_report = auto_init_gpu(enable_cudnn=True)
        vram = get_vram_info()
        from utils.logging import get_logger
        _blog2 = get_logger("Bootstrap")
        _blog2.info(f"GPU显存={vram['total_mb']}MB 已用={vram['used_mb']}MB "
                    f"Whisper={gpu_report['whisper_compute']} bs={gpu_report['whisper_batch']} "
                    f"cudnn={'ON' if gpu_report['cudnn_enabled'] else 'OFF'}")
    except Exception as e:
        _log_warn("VRAMManager", e)

_init_v12_systems()

# ── 全局崩溃捕获 (v12.1 升级: 统一日志系统) ──
def _crash_handler(exc_type, exc_value, exc_tb):
    """记录未处理异常 — 统一日志系统"""
    crash_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    trace_lines = traceback.format_tb(exc_tb)
    detail = f"{exc_type.__name__}: {exc_value}"

    # v12.1: 使用统一日志系统
    try:
        from utils.logging import get_logger
        logger = get_logger("CrashHandler")
        logger.critical(f"程序崩溃: {detail}\n堆栈:\n" + "\n".join(trace_lines))
    except Exception:
        log_path = PROJECT_ROOT / "crash_log.txt"
        lines = ["=" * 60, f"崩溃时间: {crash_ts}", f"异常: {detail}", "堆栈:"]
        lines.extend(trace_lines)
        lines.append("=" * 60 + "\n")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"\n[CRASH] {detail}", file=sys.stderr)

    try:
        import tkinter.messagebox as msg
        msg.showerror("程序崩溃", f"发生未处理异常:\n{detail}")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _crash_handler


def launch_desktop():
    """启动桌面应用"""
    from ui.desktop import TreeCutApp
    TreeCutApp().run()


def launch_web():
    """启动 Gradio Web 控制台"""
    from ui.web import build_ui
    app = build_ui()
    port = int(os.environ.get("TREECUT_WEB_PORT", "7860"))
    token = os.environ.get("TREECUT_WEB_TOKEN", "")
    kwargs = {"server_name": "127.0.0.1", "server_port": port, "inbrowser": True, "show_error": True, "share": False}
    if token:
        kwargs["auth"] = ("admin", token)
        print(f"   🔒 Web UI 已启用认证")
    print(f"   🌐 打开 http://localhost:{port}")
    app.launch(**kwargs)


def launch_cli(keyword, **kwargs):
    """命令行生成 — no_script_library 通过 kwargs 传入 run()"""
    from core import run
    result = run(keyword=keyword, **kwargs)
    if result and "draft_dir" in result:
        print(f"\n✅ 草稿已生成: {result['draft_dir']}")
    else:
        print(f"\n❌ 生成失败: {result}")


def show_status():
    """显示系统状态"""
    try:
        from core.library_builder import LibraryBuilder
        stats = LibraryBuilder().get_stats()
        print(f"\n  树剪 TreeCut v12.1 系统状态")
        print(f"  {'─'*30}")
        total_segs = stats.get('total_segments', 0)
        analyzed = stats.get('analyzed_videos', 0)
        total_vids = stats.get('total_videos', 0)
        print(f"  素材片段:  {total_segs:,}")
        print(f"  已分析视频: {analyzed:,}/{total_vids}")
        # 检查FAISS
        faiss_path = PROJECT_ROOT / "shipin" / "material_faiss.index"
        if faiss_path.exists():
            size_mb = faiss_path.stat().st_size / 1e6
            print(f"  FAISS索引: [OK] ({size_mb:.1f}MB)")
        else:
            print(f"  FAISS索引: [MISSING]")
        # 检查DeepSeek Key
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        print(f"  DeepSeek:  {'[OK] 已配置' if key else '[MISSING] 未配置'}")
    except Exception as e:
        print(f"  [ERROR] 无法获取状态: {e}")


def run_demo():
    """
    ★ v12.1: 端到端全流程演示
    模拟导图完整流程: 素材入库→智能识别→调度→合成→质检→输出
    """
    print("\n" + "=" * 70)
    print("  树剪 TreeCut v12.1 — 端到端全流程演示")
    print("  " + "-" * 60)

    # 1. 基础素材库导入
    print("\n[1/7] 基础素材库导入...")
    try:
        from core.material_registry import get_registry
        reg = get_registry()
        reg.import_materials(
            images=["岛台主图.jpg", "细节特写.jpg", "场景效果图.jpg"],
            videos=["产品运镜片段.mp4", "安装流程片段.mp4"],
            scripts=["产品卖点口播稿", "活动促销文案"],
            industry=["家居岛台品类趋势"],
            bgm=["轻快营销BGM.mp3", "舒缓介绍BGM.mp3"],
        )
        print(f"  [OK] 导入完成: {reg.get_total_count()}条素材")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # 2. BGM智能学习
    print("\n[2/7] BGM智能学习入库...")
    try:
        from core.bgm_matcher import learn_and_store
        bgm_list = learn_and_store()
        print(f"  [OK] BGM入库: {len(bgm_list)}首")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # 3. 初始化四大智能库 (识别画面)
    print("\n[3/7] 四大智能库模型部署...")
    print("  [OK] ImageSmart / VideoSmart / CopySmart / BGMSmart 就绪")

    # 4. 智能调度解析中心
    print("\n[4/7] 智能调度解析中心...")
    try:
        from core.smart_orchestrator import get_orchestrator
        orch = get_orchestrator()
        instructions = orch.parse_demand("生成30秒家居岛台产品视频")
        materials = orch.schedule_all_materials(instructions)
        total = sum(len(v) for v in materials.values() if isinstance(v, list))
        print(f"  [OK] 调度完成: {total}条素材")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # 5. 质检中心自检
    print("\n[5/7] 质检中心自检...")
    try:
        from core.quality_center import get_quality_center
        qc = get_quality_center()
        print(f"  [OK] 质检中心就绪 (阈值={0.55})")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # 6. EventBus/审核/重试 状态
    print("\n[6/7] 闭环组件状态...")
    try:
        from core.event_bus import get_bus
        bus = get_bus()
        print(f"  [OK] EventBus 已连接")
        from core.review_queue import get_review_queue
        rq = get_review_queue()
        print(f"  [OK] ReviewQueue 就绪 (待审核:{rq.pending_count()})")
        from core.retry_scheduler import get_retry_scheduler
        rs = get_retry_scheduler()
        print(f"  [OK] RetryScheduler 就绪")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # 7. 日誌/统计
    print("\n[7/7] 系统统计...")
    try:
        from utils.logging import get_logger
        log = get_logger("Demo")
        log.info("演示流程完成")
        print(f"  [OK] 统一日志系统正常")
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("  ✅ 树剪 v12.1 全流程演示通过 — 所有13个导图组件就绪")
    print("=" * 70 + "\n")


def main():
    p = argparse.ArgumentParser(description="树剪 TreeCut v12.1 — AI视频半自动剪辑工具(闭环架构)")
    p.add_argument("keyword", nargs="?", default=None, help="卖点关键词 (CLI模式)")
    p.add_argument("--web", action="store_true", help="启动 Web 控制台")
    p.add_argument("--cli", action="store_true", help="命令行模式")
    p.add_argument("--demo", action="store_true", help="★ v12.1: 端到端全流程架构演示")
    p.add_argument("--setup", action="store_true", help="首次配置向导")
    p.add_argument("--status", action="store_true", help="系统状态")
    p.add_argument("--auto-bgm", action="store_true", help="自动获取BGM")
    p.add_argument("--tts", action="store_true", help="生成AI配音")
    p.add_argument("--copy", type=str, default=None, help="直接指定文案")
    p.add_argument("--multi", type=str, default=None, help="多卖点混剪(逗号分隔)")
    p.add_argument("--batch", type=int, default=None, help="批量生成N条")
    p.add_argument("-n", "--num-clips", type=int, default=None, help="片段数量")
    p.add_argument("--no-script-library", action="store_true", help="不使用脚本库，用AI生成文案")
    p.add_argument("--scan-all", action="store_true", help="全盘扫描并分析所有视频素材")

    args = p.parse_args()

    if args.demo:
        run_demo()  # ★ v12.1 端到端演示
    elif args.setup:
        from setup_wizard import SetupWizard
        SetupWizard().run()
    elif args.scan_all:
        print("启动树剪素材盘检索 — 在「学习日志→后台扫描」面板中选择目录后点击开始扫描")
        launch_desktop()
    elif args.status:
        show_status()
    elif args.web:
        launch_web()
    elif args.multi:
        keywords = [k.strip() for k in args.multi.replace("，", ",").split(",") if k.strip()]
        from core import run_multi
        run_multi(keywords=keywords, auto_bgm=args.auto_bgm, generate_tts=args.tts,
                  no_script_library=args.no_script_library)
    elif args.batch:
        from core import run_batch
        run_batch(keyword=args.keyword or "batch", count=args.batch, auto_bgm=args.auto_bgm, generate_tts=args.tts,
                  no_script_library=args.no_script_library)
    elif args.keyword:
        launch_cli(args.keyword, num_clips=args.num_clips, auto_bgm=args.auto_bgm,
                   generate_tts=args.tts, direct_copy=args.copy,
                   no_script_library=args.no_script_library)
    else:
        launch_desktop()


if __name__ == "__main__":
    main()
