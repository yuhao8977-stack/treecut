# -*- coding: utf-8 -*-
"""树剪 v3.0"""
import os as _os, sys as _sys, traceback as _tb, datetime as _dt
# ====== 崩溃追踪：第1行就写日志 ======
_LOG = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "logs")
_os.makedirs(_LOG, exist_ok=True)
_LOG_FILE = _os.path.join(_LOG, f"startup_{_dt.datetime.now().strftime('%H%M%S')}.log")
def _log(msg):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{_dt.datetime.now().strftime('%H:%M:%S.%f')}] {msg}\n")
    except:
        pass
_log(f"PID={_os.getpid()} Python={_sys.version[:30]} CWD={_os.getcwd()}")
_log(f"Args={_sys.argv}")
# ====== 防护 ======
for _k, _v in {"MPLBACKEND":"Agg","MATPLOTLIBRC":"Agg","QT_QPA_PLATFORM":"offscreen","SDL_VIDEODRIVER":"dummy","PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}.items():
    _os.environ[_k] = _v
_sys.dont_write_bytecode = True
_log("Env+bytecode set")
# 清理缓存
import shutil as _su
_rd = _os.path.dirname(_os.path.abspath(__file__))
for _r, _ds, _fs in _os.walk(_rd):
    if "__pycache__" in _ds:
        _su.rmtree(_os.path.join(_r, "__pycache__"), ignore_errors=True)
_log("Cache cleaned")
# matplotlib
try:
    import matplotlib as _mpl; _mpl.use("Agg", force=True)
    _log(f"matplotlib backend={_mpl.get_backend()}")
except Exception as _e:
    _log(f"matplotlib skip: {_e}")
# ====== 正式导入（每步都写日志） ======
import argparse
if _sys.platform == "win32":
    try:
        import io
        _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
        _sys.stderr = io.TextIOWrapper(_sys.stderr.buffer, encoding="utf-8", errors="replace")
    except: pass
try:
    _log("import config_loader...")
    from core.config_loader import CONFIG
    _log("config_loader OK")
    _log("import database...")
    from core.database import init_db, query_sql, execute_sql
    _log("database OK")
    _log("import logger...")
    from utils.logging import get_loguru_logger as get_logger
    _log("logger OK")
    _log("import system_optimizer...")
    from utils.system_optimizer import optimize_for_hardware
    _log("system_optimizer OK")
    _log("import vram_manager...")
    from utils.vram_manager import init_cuda_environment
    _log("vram_manager OK")
    logger = get_logger("main")
    _log("All core imports done ✓")
except Exception as _e:
    _log(f"CORE IMPORT FAILED: {_e}\n{_tb.format_exc()}")
    raise
def cmd_init(args):
    _log("cmd_init start")
    logger.info("=" * 50)
    logger.info(f"树剪 v{CONFIG['system']['version']} 环境初始化")
    logger.info("=" * 50)
    for d in ["data","data/db","data/models","data/materials","data/features","data/output/corrected","data/logs","data/brand_logos","config"]:
        _os.makedirs(d, exist_ok=True)
        logger.info(f"  [OK] {d}")
    if init_db():
        logger.info("  [OK] 数据库初始化完成")
    try:
        import psutil
        logger.info(f"  CPU: {psutil.cpu_percent()}% | 内存: {psutil.virtual_memory().available//(1024**3)}GB可用")
    except: pass
    init_cuda_environment(CONFIG["performance"]["enable_cudnn_benchmark"])
    logger.info("初始化完成！")
    _log("cmd_init done")
    return True
def cmd_process(args):
    video_path = args.input
    if not _os.path.exists(video_path):
        logger.error(f"文件不存在: {video_path}")
        return False
    init_db()
    abs_path = _os.path.abspath(video_path)
    existing = query_sql("SELECT id FROM materials WHERE file_path=?", (abs_path,))
    if existing:
        mid = existing[0][0]
        execute_sql("UPDATE materials SET status='pending' WHERE id=?", (mid,))
    else:
        from utils.ffmpeg_utils import get_video_info
        info = get_video_info(abs_path)
        mid = execute_sql(
            "INSERT INTO materials (file_path,file_type,duration,resolution,fps,bitrate,status) VALUES (?,?,?,?,?,?,'pending')",
            (abs_path,"video",info.get("duration",0),info.get("resolution",""),info.get("fps",0),info.get("bitrate",0)))
    logger.info(f"处理: {_os.path.basename(video_path)} | ID: {mid}")
    _log(f"cmd_process: {abs_path} id={mid}")
    from core.workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    import time; t0 = time.time()
    try:
        result = engine.run(mid, abs_path)
        elapsed = time.time() - t0
        if result["status"] == "success":
            logger.info(f"完成! {elapsed:.1f}s | 剩余问题: {result.get('remaining_issues',0)}个")
            return True
        else:
            logger.error(f"失败: {result.get('error','unknown')}")
            return False
    finally: pass
def cmd_batch(args):
    from tasks.task_queue import task_queue
    count = task_queue.add_folder(args.batch)
    logger.info(f"导入{count}个素材")
    total = task_queue.run_all()
    logger.info(f"批量完成: {total}个")
    return total > 0
def cmd_status(args):
    init_db()
    materials = query_sql("SELECT id,file_path,status,duration,resolution FROM materials ORDER BY id DESC LIMIT 20")
    if not materials:
        logger.info("暂无记录")
        return True
    logger.info("=" * 70)
    logger.info(f"{'ID':<6} {'状态':<12} {'时长':<10} {'分辨率':<15} {'文件'}")
    logger.info("-" * 70)
    for m in materials:
        logger.info(f"{m[0]:<6} {m[2]:<12} {m[3] or 0:<10.1f} {m[4] or '未知':<15} {_os.path.basename(m[1])}")
    issues = query_sql("SELECT check_type,issue_level,COUNT(*) as cnt FROM quality_results GROUP BY check_type,issue_level")
    if issues:
        logger.info("-" * 70)
        for row in issues:
            logger.info(f"  {row[0]} [{row[1]}]: {row[2]}个")
    return True
def main():
    _log("main() start")
    parser = argparse.ArgumentParser(description="树剪 v3.0")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--input","-i",type=str)
    parser.add_argument("--batch","-b",type=str)
    parser.add_argument("--run",type=int)
    parser.add_argument("--run-all",action="store_true")
    parser.add_argument("--status","-s",action="store_true")
    parser.add_argument("--list",action="store_true")
    parser.add_argument("--dashboard",action="store_true")
    parser.add_argument("--verbose","-v",action="store_true")
    args = parser.parse_args()
    _log(f"Parsed args: {args}")
    _log("optimize_for_hardware...")
    optimize_for_hardware(CONFIG)
    _log("init_cuda_environment...")
    init_cuda_environment(CONFIG["performance"]["enable_cudnn_benchmark"])
    _log("Both OK")
    if args.init:           return cmd_init(args)
    elif args.input:        return cmd_process(args)
    elif args.batch:        return cmd_batch(args)
    elif args.run_all:
        from tasks.task_queue import task_queue; return task_queue.run_all() > 0
    elif args.run:
        from core.workflow_engine import WorkflowEngine
        init_db()
        row = query_sql("SELECT file_path FROM materials WHERE id=?",(args.run,))
        if row:
            engine = WorkflowEngine()
            result = engine.run(args.run, row[0][0])
            return result["status"] == "success"
        return False
    elif args.status or args.list:
        return cmd_status(args)
    elif args.dashboard:
        import subprocess
        subprocess.run([sys.executable,"-m","streamlit","run","dashboard/app.py"])
        return True
    else:
        parser.print_help()
        return True
if __name__ == "__main__":
    try:
        _log("Entering main()")
        ok = main()
        _log(f"Exit: {'OK' if ok else 'FAIL'}")
        _sys.exit(0 if ok else 1)
    except Exception as e:
        _log(f"CRASH: {type(e).__name__}: {e}\n{_tb.format_exc()}")
        print(f"\n[错误] {type(e).__name__}: {e}")
        _tb.print_exc()
        _sys.exit(1)
