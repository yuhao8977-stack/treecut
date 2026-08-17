; 树剪 TreeCut — Inno Setup 安装包脚本
; 用法: 下载安装 Inno Setup (https://jrsoftware.org/isinfo.php)
;       用 Inno Setup Compiler 打开此文件 → Build → Compile
; 输出: Output\树剪TreeCut_Setup_v10.3.exe

#define MyAppName "树剪 TreeCut"
#define MyAppVersion "10.3"
#define MyAppPublisher "坤宝岛台"
#define MyAppExeName "树剪TreeCut.exe"

[Setup]
AppId={{AD7B8C3E-5D2A-4F11-9E3B-7C6D5A4F3E2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=树剪TreeCut_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "startmenu"; Description: "创建开始菜单文件夹"; GroupDescription: "附加图标:"

[Files]
; 主程序（需先用 build_exe.py 打包）
Source: "dist\树剪TreeCut.exe"; DestDir: "{app}"; Flags: ignoreversion

; 配置文件
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: ignoreversion onlyifdoesntexist
Source: "protected_words.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "tree_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; 可选: 预置素材（如果打包时已存在）
Source: "02_BGM\*"; DestDir: "{app}\02_BGM"; Flags: ignoreversion skipifsourcedoesntexist
Source: "ai_material_library.db"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\配置向导"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// 首次安装后提示配置 API Key
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    MsgBox('安装完成！使用前请配置:' + #13#10 +
           '1. 将 DeepSeek API Key 填入 ' + ExpandConstant('{app}') + '\.env' + #13#10 +
           '2. 确保 Z:\已处理素材 路径可访问' + #13#10 +
           '   或在首次运行时设置素材路径', mbInformation, MB_OK);
  end;
end;
