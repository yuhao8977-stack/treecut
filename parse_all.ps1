# 解析三个文件并保存结果
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Xml

$outputFile = "E:\树剪软件相关文件\解析结果.txt"
$writer = [System.IO.StreamWriter]::new($outputFile, $false, [System.Text.Encoding]::UTF8)

function Parse-Docx {
    param($filepath)
    $zip = [System.IO.Compression.ZipFile]::OpenRead($filepath)
    $entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' }
    $reader = New-Object System.IO.StreamReader($entry.Open())
    $xmlContent = $reader.ReadToEnd()
    $reader.Close()
    $zip.Dispose()
    
    $xml = [xml]$xmlContent
    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main")
    
    $paragraphs = @()
    foreach ($p in $xml.SelectNodes('//w:p', $ns)) {
        $text = ''
        foreach ($t in $p.SelectNodes('.//w:t', $ns)) {
            $text += $t.InnerText
        }
        if ($text.Trim()) {
            $paragraphs += $text
        }
    }
    return $paragraphs
}

function Parse-Xlsx {
    param($filepath)
    $zip = [System.IO.Compression.ZipFile]::OpenRead($filepath)
    
    # 读取共享字符串
    $sharedStrings = @()
    $ssEntry = $zip.Entries | Where-Object { $_.FullName -eq 'xl/sharedStrings.xml' }
    if ($ssEntry) {
        $reader = New-Object System.IO.StreamReader($ssEntry.Open())
        $ssXml = [xml]$reader.ReadToEnd()
        $reader.Close()
        $ns = New-Object System.Xml.XmlNamespaceManager($ssXml.NameTable)
        $ns.AddNamespace("ns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
        foreach ($si in $ssXml.SelectNodes('//ns:si', $ns)) {
            $text = ''
            foreach ($t in $si.SelectNodes('.//ns:t', $ns)) {
                $text += $t.InnerText
            }
            $sharedStrings += $text
        }
    }
    
    # 读取所有工作表
    $sheets = @()
    $sheetEntries = $zip.Entries | Where-Object { $_.FullName -like 'xl/worksheets/sheet*.xml' } | Sort-Object FullName
    
    foreach ($sheetEntry in $sheetEntries) {
        $reader = New-Object System.IO.StreamReader($sheetEntry.Open())
        $sheetXml = [xml]$reader.ReadToEnd()
        $reader.Close()
        
        $ns = New-Object System.Xml.XmlNamespaceManager($sheetXml.NameTable)
        $ns.AddNamespace("ns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
        
        $rows = @()
        foreach ($row in $sheetXml.SelectNodes('//ns:row', $ns)) {
            $rowNum = [int]$row.GetAttribute('r')
            $cells = @{}
            foreach ($c in $row.SelectNodes('ns:c', $ns)) {
                $cellRef = $c.GetAttribute('r')
                $cellType = $c.GetAttribute('t')
                $vNode = $c.SelectSingleNode('ns:v', $ns)
                $value = if ($vNode) { $vNode.InnerText } else { '' }
                
                if ($cellType -eq 's' -and $value -match '^\d+$') {
                    $idx = [int]$value
                    if ($idx -lt $sharedStrings.Count) {
                        $value = $sharedStrings[$idx]
                    }
                }
                $cells[$cellRef] = $value
            }
            $rows += @{ RowNum = $rowNum; Cells = $cells }
        }
        $sheets += @{ Name = $sheetEntry.Name; Rows = $rows }
    }
    
    $zip.Dispose()
    return $sheets
}

# 解析Word文档
$writer.WriteLine("=" * 80)
$writer.WriteLine("=== 树剪_TreeCut_程序详细说明文档.docx ===")
$writer.WriteLine("=" * 80)
$docxParas = Parse-Docx "E:\树剪软件相关文件\树剪_TreeCut_程序详细说明文档.docx"
$writer.WriteLine("共 $($docxParas.Count) 个段落")
for ($i = 0; $i -lt $docxParas.Count; $i++) {
    $writer.WriteLine()
    $writer.WriteLine("[$($i+1)] $($docxParas[$i])")
}

# 解析Excel第1部分
$writer.WriteLine()
$writer.WriteLine("=" * 80)
$writer.WriteLine("=== 树剪_v3.0_代码_第1部分.xlsx ===")
$writer.WriteLine("=" * 80)
$xlsx1 = Parse-Xlsx "E:\树剪软件相关文件\树剪_v3.0_代码_第1部分.xlsx"
foreach ($sheet in $xlsx1) {
    $writer.WriteLine()
    $writer.WriteLine("--- $($sheet.Name) (共 $($sheet.Rows.Count) 行) ---")
    foreach ($row in $sheet.Rows) {
        $a = $row.Cells["A$($row.RowNum)"]
        $b = $row.Cells["B$($row.RowNum)"]
        $c = $row.Cells["C$($row.RowNum)"]
        $writer.WriteLine("行$($row.RowNum): A=$a | B=$b | C=$c")
    }
}

# 解析Excel第2部分
$writer.WriteLine()
$writer.WriteLine("=" * 80)
$writer.WriteLine("=== 树剪_v3.0_代码_第2部分.xlsx ===")
$writer.WriteLine("=" * 80)
$xlsx2 = Parse-Xlsx "E:\树剪软件相关文件\树剪_v3.0_代码_第2部分.xlsx"
foreach ($sheet in $xlsx2) {
    $writer.WriteLine()
    $writer.WriteLine("--- $($sheet.Name) (共 $($sheet.Rows.Count) 行) ---")
    foreach ($row in $sheet.Rows) {
        $a = $row.Cells["A$($row.RowNum)"]
        $b = $row.Cells["B$($row.RowNum)"]
        $c = $row.Cells["C$($row.RowNum)"]
        $writer.WriteLine("行$($row.RowNum): A=$a | B=$b | C=$c")
    }
}

$writer.Close()
Write-Host "解析完成，结果已保存到: $outputFile"
Write-Host "文件大小: $((Get-Item $outputFile).Length) 字节"
