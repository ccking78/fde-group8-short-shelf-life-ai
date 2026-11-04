$ErrorActionPreference = 'Stop'
$taskOutput = 'F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103'
$taskWord = $null
try {
    $taskWord = New-Object -ComObject Word.Application
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskWord.AutomationSecurity = 3
    foreach ($taskFile in (Get-ChildItem -LiteralPath $taskOutput -Filter '*.docx')) {
        $taskDoc = $null
        try {
            $taskDoc = $taskWord.Documents.Open($taskFile.FullName, $false, $true)
            $taskDoc.Repaginate()
            $taskPdf = [System.IO.Path]::ChangeExtension($taskFile.FullName, '.pdf')
            $taskDoc.ExportAsFixedFormat($taskPdf, 17)
            [PSCustomObject]@{Name=$taskFile.Name;Pages=$taskDoc.ComputeStatistics(2);PDF=$taskPdf}
        } finally {
            if ($null -ne $taskDoc) { $taskDoc.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskDoc) }
        }
    }
} finally {
    if ($null -ne $taskWord) { $taskWord.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskWord) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
