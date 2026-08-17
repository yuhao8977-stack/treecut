# Extract core code files for analysis
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-CodeFromSheet {
    param($zipPath, $sheetXmlPath)
    
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    $entry = $zip.Entries | Where-Object { $_.FullName -eq $sheetXmlPath }
    if (-not $entry) {
        $zip.Dispose()
        return @()
    }
    
    $reader = New-Object System.IO.StreamReader($entry.Open())
    $xmlContent = $reader.ReadToEnd()
    $reader.Close()
    $zip.Dispose()
    
    $xml = [xml]$xmlContent
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("ns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    
    $codeLines = @()
    $rows = $xml.SelectNodes("//ns:row", $ns)
    
    foreach ($row in $rows) {
        $rowNum = [int]$row.GetAttribute("r")
        if ($rowNum -le 3) { continue }
        
        $cells = $row.SelectNodes("ns:c", $ns)
        $lineNum = ""
        $code = ""
        
        foreach ($cell in $cells) {
            $ref = $cell.GetAttribute("r")
            $cellType = $cell.GetAttribute("t")
            
            if ($ref -like "A*") {
                $vNode = $cell.SelectSingleNode("ns:v", $ns)
                if ($vNode) { $lineNum = $vNode.InnerText }
            }
            elseif ($ref -like "B*") {
                if ($cellType -eq "inlineStr") {
                    $isNode = $cell.SelectSingleNode("ns:is", $ns)
                    if ($isNode) {
                        $tNodes = $isNode.SelectNodes("ns:t", $ns)
                        foreach ($t in $tNodes) {
                            $code += $t.InnerText
                        }
                    }
                }
                else {
                    $vNode = $cell.SelectSingleNode("ns:v", $ns)
                    if ($vNode) { $code = $vNode.InnerText }
                }
            }
        }
        
        if ($code -ne "") {
            $codeLines += @{ Line = $lineNum; Code = $code }
        }
    }
    
    return $codeLines
}

function Get-SheetXmlPath {
    param($zipPath, $sheetName)
    
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    
    $wbEntry = $zip.Entries | Where-Object { $_.FullName -eq "xl/workbook.xml" }
    $reader = New-Object System.IO.StreamReader($wbEntry.Open())
    $wbXml = [xml]$reader.ReadToEnd()
    $reader.Close()
    
    $ns = New-Object System.Xml.XmlNamespaceManager($wbXml.NameTable)
    $ns.AddNamespace("ns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    
    $sheet = $wbXml.SelectSingleNode("//ns:sheet[@name=`"$sheetName`"]", $ns)
    if (-not $sheet) {
        $zip.Dispose()
        return $null
    }
    
    $sheetId = $sheet.GetAttribute("sheetId")
    
    $relsEntry = $zip.Entries | Where-Object { $_.FullName -eq "xl/_rels/workbook.xml.rels" }
    $reader = New-Object System.IO.StreamReader($relsEntry.Open())
    $relsContent = $reader.ReadToEnd()
    $reader.Close()
    $zip.Dispose()
    
    $relsXml = [xml]$relsContent
    $ns2 = New-Object System.Xml.XmlNamespaceManager($relsXml.NameTable)
    $ns2.AddNamespace("ns", "http://schemas.openxmlformats.org/package/2006/relationships")
    
    $rel = $relsXml.SelectSingleNode("//ns:Relationship[@Id=`"rId$sheetId`"]", $ns2)
    if (-not $rel) { return $null }
    
    $target = $rel.GetAttribute("Target")
    if ($target.StartsWith("/")) {
        $target = $target.Substring(1)
    }
    
    return $target
}

$coreFiles = @(
    @{ Name = "core_pipeline_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_core_pipeline.py" },
    @{ Name = "core_config_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_core_config.py" },
    @{ Name = "core_database_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_core_database.py" },
    @{ Name = "main_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_main.py" },
    @{ Name = "core_copywriter_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_core_copywriter.py" },
    @{ Name = "core_tts_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_core_tts.py" },
    @{ Name = "core_draft_py"; Zip = "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"; Output = "E:\树剪软件相关文件\code_core_draft.py" }
)

foreach ($file in $coreFiles) {
    Write-Host "Extracting: $($file.Name)..."
    $sheetPath = Get-SheetXmlPath $file.Zip $file.Name
    if (-not $sheetPath) {
        Write-Host "  Sheet not found: $($file.Name)"
        continue
    }
    
    $codeLines = Get-CodeFromSheet $file.Zip $sheetPath
    if ($codeLines.Count -eq 0) {
        Write-Host "  No code extracted"
        continue
    }
    
    $writer = [System.IO.StreamWriter]::new($file.Output, $false, [System.Text.Encoding]::UTF8)
    foreach ($line in $codeLines) {
        $writer.WriteLine($line.Code)
    }
    $writer.Close()
    
    Write-Host "  Done: $($codeLines.Count) lines -> $($file.Output)"
}

Write-Host ""
Write-Host "All core files extracted!"
