@echo off
chcp 65001 >nul
title ModelScope 下载 Qwen3-VL-4B-FP8

cd /d "E:\树剪软件相关文件"

set PYTHON=C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe

echo ============================================
echo   ModelScope 国内源下载 Qwen3-VL-4B-FP8
echo ============================================
echo.

echo [1/2] 安装 modelscope...
%PYTHON% -m pip install modelscope -q

echo.
echo [2/2] 开始下载 (约4GB, 支持断点续传)...
%PYTHON% -m modelscope download --model Qwen/Qwen3-VL-4B-Instruct-FP8 --local_dir ./Qwen3-VL-4B-Instruct-FP8

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo   下载完成!
    echo ============================================
) else (
    echo.
    echo 下载中断, 重新运行此脚本可断点续传
)
pause
