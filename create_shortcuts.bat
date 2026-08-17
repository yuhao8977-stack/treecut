@echo off
chcp 65001 >nul
title 树剪 TreeCut — 创建快捷方式

:: ============================================================
:: 树剪 TreeCut — 安装后自动生成桌面快捷方式
:: 用法: 双击运行，或在 Inno Setup 中作为 post-install 脚本
:: ============================================================

setlocal enabledelayedexpansion

:: 获取脚本所在目录（即安装目录）
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

:: 查找 Python
set "PYTHON="
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
    "%PROGRAMFILES%\Python312\pythonw.exe"
    "%PROGRAMFILES%\Python311\pythonw.exe"
) do (
    if exist %%p (
        set "PYTHON=%%p"
        goto :found_python
    )
)

:: 如果没找到特定版本，尝试从 PATH 中找
where pythonw >nul 2>&1
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where pythonw') do set "PYTHON=%%i"
    goto :found_python
)

echo [WARN] 未找到 pythonw.exe，请先安装 Python 3.12
echo       下载: https://www.python.org/downloads/
pause
exit /b 1

:found_python
echo  Python: %PYTHON%
echo  安装目录: %APP_DIR%

:: 获取桌面路径（支持中文和英文系统）
for /f "tokens=2*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul') do set "DESKTOP=%%b"
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"
echo  桌面路径: %DESKTOP%

:: 获取开始菜单路径
for /f "tokens=2*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v "Programs" 2^>nul') do set "STARTMENU=%%b"
if not defined STARTMENU set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
echo  开始菜单: %STARTMENU%

:: ============================================================
:: 创建桌面快捷方式
:: ============================================================
echo.
echo  正在创建桌面快捷方式...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$ws = New-Object -ComObject WScript.Shell; ^
$lnk = $ws.CreateShortcut('%DESKTOP%\树剪 TreeCut.lnk'); ^
$lnk.TargetPath = '%PYTHON%'; ^
$lnk.Arguments = '树剪.py'; ^
$lnk.WorkingDirectory = '%APP_DIR%'; ^
$lnk.IconLocation = '%APP_DIR%\tree_icon.ico'; ^
$lnk.Description = '树剪 TreeCut v10.3 - AI视频半自动剪辑工具'; ^
$lnk.Save()"

if %errorlevel%==0 (
    echo    ✅ 桌面快捷方式已创建
) else (
    echo    ❌ 创建失败，尝试备用方法...
    :: 备用：使用 mklink (需要管理员权限)
    mklink "%DESKTOP%\树剪 TreeCut.lnk" "%APP_DIR%\树剪.py" >nul 2>&1
)

:: ============================================================
:: 创建开始菜单文件夹和快捷方式
:: ============================================================
echo  正在创建开始菜单快捷方式...

set "SM_DIR=%STARTMENU%\树剪 TreeCut"
if not exist "%SM_DIR%" mkdir "%SM_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$ws = New-Object -ComObject WScript.Shell; ^
$lnk = $ws.CreateShortcut('%SM_DIR%\树剪 TreeCut.lnk'); ^
$lnk.TargetPath = '%PYTHON%'; ^
$lnk.Arguments = '树剪.py'; ^
$lnk.WorkingDirectory = '%APP_DIR%'; ^
$lnk.IconLocation = '%APP_DIR%\tree_icon.ico'; ^
$lnk.Description = '树剪 TreeCut - AI视频半自动剪辑工具'; ^
$lnk.Save(); ^
$lnk2 = $ws.CreateShortcut('%SM_DIR%\配置向导.lnk'); ^
$lnk2.TargetPath = '%PYTHON%'; ^
$lnk2.Arguments = 'setup_wizard.py'; ^
$lnk2.WorkingDirectory = '%APP_DIR%'; ^
$lnk2.IconLocation = '%APP_DIR%\tree_icon.ico'; ^
$lnk2.Description = '树剪 首次配置向导'; ^
$lnk2.Save()"

if %errorlevel%==0 (
    echo    ✅ 开始菜单已创建
) else (
    echo    ⚠ 开始菜单创建失败（非关键）
)

echo.
echo ══════════════════════════════════════════════
echo   ✅ 快捷方式创建完成！
echo.
echo   桌面: 树剪 TreeCut
echo   开始菜单: 树剪 TreeCut\树剪 TreeCut
echo   开始菜单: 树剪 TreeCut\配置向导
echo ══════════════════════════════════════════════
echo.
echo   首次使用请先运行「配置向导」设置 API Key
echo   或直接启动后在 .env 文件中配置

endlocal
pause
