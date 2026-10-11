# Checks the Cambridge Dictionary and BBC links in app/content/lessons/*.json by their page title.
# A wrong Cambridge URL still answers 200, but with the generic title
# "English Grammar Today on Cambridge Dictionary" — so the title is what counts.
# British Council pages refuse these requests from this machine: check those with WebFetch.
# Usage: powershell -File dev\tests\sources_check.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$bad = 0; $ok = 0
foreach ($file in Get-ChildItem "$root\app\content\lessons\*.json") {
    $data = Get-Content $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($lesson in $data.lessons) {
        foreach ($s in $lesson.sources) {
            if ($s.url -notmatch "dictionary\.cambridge\.org|bbc\.co\.uk") { continue }
            try {
                $r = Invoke-WebRequest $s.url -UseBasicParsing -TimeoutSec 25 -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                $title = [regex]::Match($r.Content, "<title>([^<]*)").Groups[1].Value.Trim()
                if ($title -match "English Grammar Today on Cambridge Dictionary" -or -not $title) {
                    "GENERIC  $($lesson.id)  $($s.url)"; $bad++
                } else { $ok++ }
            } catch {
                "ERROR    $($lesson.id)  $($s.url)  $($_.Exception.Message)"; $bad++
            }
        }
    }
}
"$ok bağlantı doğru, $bad sorunlu"
