@echo off
cd /d "E:\树剪软件相关文件"
set PYTHON=C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe

echo === ModelScope Download Qwen3-VL-4B-FP8 ===
echo.

%PYTHON% -m pip install modelscope -q

echo Starting download (~4GB, resumable)...
echo.

modelscope download --model Qwen/Qwen3-VL-4B-Instruct-FP8 --local_dir Qwen3-VL-4B-Instruct-FP8

echo.
echo Done! Check with: python verify_models.py
pause
