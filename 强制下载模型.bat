@echo off
chcp 65001 >nul
title 树剪 AI模型强制下载 (HF镜像加速)

echo ============================================
echo   树剪 TreeCut - 视觉模型强制下载
echo   使用 HuggingFace 镜像加速
echo ============================================
echo.

set HF_ENDPOINT=https://hf-mirror.com

echo [1/2] 安装依赖...
C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe -m pip install huggingface_hub -q

echo.
echo [2/2] 开始下载模型到 models/ 目录...
echo.

C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe -c "import os; os.environ['HF_ENDPOINT']='https://hf-mirror.com'; from huggingface_hub import snapshot_download; from pathlib import Path; models_dir=Path('models'); print('Downloading Florence-2-base (0.5GB)...'); snapshot_download('microsoft/Florence-2-base', local_dir=str(models_dir/'Florence-2-base'), local_dir_use_symlinks=False, resume_download=True); print('Florence-2: OK'); print('Downloading Qwen3-VL-3B (6GB)...'); snapshot_download('Qwen/Qwen3-VL-3B', local_dir=str(models_dir/'Qwen3-VL-3B'), local_dir_use_symlinks=False, resume_download=True); print('Qwen3-3B: OK'); print(); print('All models downloaded!')"

echo.
echo ============================================
echo   下载完成! 模型保存在 models/ 目录
echo ============================================
pause
