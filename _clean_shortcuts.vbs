Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
Set WshEnv = WshShell.Environment("Process")
desktop = WshShell.SpecialFolders("Desktop")

' Delete broken shortcuts
For Each lnk In Array("树剪.lnk", "树剪看板.lnk", "树剪_v3.0.lnk")
    path = desktop + "\" + lnk
    If fso.FileExists(path) Then
        fso.DeleteFile path, True
    End If
Next

' Create ONE working shortcut
Set lnk = WshShell.CreateShortcut(desktop + "\树剪.lnk")
lnk.TargetPath = "E:\树剪软件相关文件\启动树剪.bat"
lnk.WorkingDirectory = "E:\树剪软件相关文件"
lnk.WindowStyle = 1
lnk.Description = "树剪 TreeCut - AI视频剪辑工具"
lnk.IconLocation = "E:\树剪软件相关文件\tree_icon.ico,0"
lnk.Save()

WScript.Echo "Shortcuts cleaned. Created: 树剪.lnk"
