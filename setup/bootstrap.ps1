# Kurulum.bat önyüklemesi: gömülü Python'u hazırlar ve kurulum sihirbazını açar.
# Sisteme hiçbir şey kurmaz; her şey bu klasörün içine iner.
# Kurulum.bat'a verilen argümanlar sihirbaza iletilir (ör. --no-browser, --mode maintenance).
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$WizardArgs)

# Native programs (curl, python) report through $LASTEXITCODE; with "Stop", PowerShell 5.1
# would abort on any line they write to stderr. Cmdlets use -ErrorAction Stop explicitly.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# setup.log in UTF-8 (5.1 defaults: Add-Content = ANSI, ">>" = UTF-16 → mixed, unreadable Turkish).
$PSDefaultParameterValues['Add-Content:Encoding'] = 'utf8'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'

$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root "runtime\python\python.exe"
$PyDir = Join-Path $Root "runtime\python"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $Logs | Out-Null
$Log = Join-Path $Logs "setup.log"
$PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

function Step($n, $text) { Write-Host ""; Write-Host "[$n/6] $text" -ForegroundColor Cyan; Add-Content $Log "$(Get-Date -f s) [$n/6] $text" }
function Info($text) { Write-Host "      $text"; Add-Content $Log "$(Get-Date -f s)   $text" }
function Fail($text) {
    Write-Host ""
    Write-Host "HATA: $text" -ForegroundColor Red
    Write-Host "Ayrıntılar: $Log"
    Add-Content $Log "$(Get-Date -f s) HATA: $text"
    exit 1
}

Write-Host "English Practice — Kurulum" -ForegroundColor Green

try {
    Step 1 "Windows kontrol ediliyor…"
    if (-not [Environment]::Is64BitOperatingSystem) { Fail "64 bit Windows gerekli." }
    if ([Environment]::OSVersion.Version.Major -lt 10) { Fail "Windows 10 veya 11 gerekli." }
    Info "Windows $([Environment]::OSVersion.Version) x64 ✓"

    Step 2 "Klasör yolu kontrol ediliyor…"
    if ($Root -match '[^\x21-\x7E\\:]' -or $Root -match ' ') {
        # Some tools break on such paths: offer to copy the folder to a safe place and go on from there.
        $Target = "C:\EnglishPractice"
        Write-Host "      Klasör yolunda Türkçe karakter veya boşluk var: $Root" -ForegroundColor Yellow
        if ((Test-Path $Target) -and (Get-ChildItem $Target -Force | Select-Object -First 1)) {
            Fail "$Target dolu. Klasörü örneğin C:\IngilizcePratik gibi bir yere taşıyıp Kurulum.bat'ı yeniden çalıştırın."
        }
        $answer = Read-Host "      Klasörü $Target konumuna kopyalayıp kuruluma oradan devam edeyim mi? (E/H)"
        if ($answer -notmatch '^[EeYy]') {
            Fail "Klasörü örneğin C:\IngilizcePratik gibi bir yere taşıyıp Kurulum.bat'ı yeniden çalıştırın."
        }
        Info "Kopyalanıyor: $Target …"
        New-Item -ItemType Directory -Force $Target -ErrorAction Stop | Out-Null
        Copy-Item -Path (Join-Path $Root "*") -Destination $Target -Recurse -Force -ErrorAction Stop
        Info "Kurulum yeni klasörde devam ediyor. Bu klasörü sonra silebilirsiniz: $Root"
        Start-Process -FilePath (Join-Path $Target "Kurulum.bat") -WorkingDirectory $Target
        exit 0
    }
    Info "$Root ✓"
    # Files from a downloaded zip are marked "from the internet" (SmartScreen warnings on Baslat.bat).
    Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

    Step 3 "İnternet ve disk alanı kontrol ediliyor…"
    $drive = Get-PSDrive -Name $Root.Substring(0, 1) -ErrorAction Stop
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    Info "Boş disk: $freeGb GB"
    if ($freeGb -lt 12) { Write-Host "      UYARI: Kurulum için en az ~12 GB boş alan önerilir." -ForegroundColor Yellow }
    $needNet = -not (Test-Path $Py)
    try {
        Invoke-WebRequest -Uri "https://www.python.org" -Method Head -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop | Out-Null
        Info "İnternet bağlantısı ✓"
    } catch {
        if ($needNet) { Fail "İnternet bağlantısı yok. Kurulum için internet gerekli (sonra çevrimdışı çalışır)." }
        Info "İnternet yok — sadece bakım işlemleri yapılabilir."
    }

    Step 4 "Python hazırlanıyor…"
    if (-not (Test-Path $Py)) {
        $zip = Join-Path $Root "models\_downloads\python-embed.zip"
        New-Item -ItemType Directory -Force (Split-Path $zip) | Out-Null
        Info "İndiriliyor (~11 MB)…"
        # curl.exe ships with Windows 10+; -C - resumes an interrupted download.
        & curl.exe -sSL -C - --retry 5 -o $zip $PythonUrl
        if ($LASTEXITCODE -ne 0) { Fail "Python indirilemedi." }
        Expand-Archive -Path $zip -DestinationPath $PyDir -Force -ErrorAction Stop
        Remove-Item $zip
        # The ._pth file decides sys.path of the embedded Python (paths relative to it).
        $pth = "python312.zip`r`n.`r`n..\..\app`r`n..\..`r`n`r`n# 'import site' enables packages installed by pip into Lib\site-packages`r`nimport site`r`n"
        [IO.File]::WriteAllText((Join-Path $PyDir "python312._pth"), $pth)
        Info "Python 3.12 ✓"
    } else {
        Info "Python zaten hazır ✓"
    }
    & $Py -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Info "pip kuruluyor…"
        $getPip = Join-Path $PyDir "get-pip.py"
        & curl.exe -sSL --retry 5 -o $getPip $GetPipUrl
        & $Py $getPip --no-warn-script-location -q *>> $Log
        if ($LASTEXITCODE -ne 0) { Fail "pip kurulamadı." }
        Remove-Item $getPip
    }
    Info "pip ✓"

    Step 5 "Sihirbaz bileşenleri kuruluyor…"
    & $Py -m pip install -q --disable-pip-version-check --no-warn-script-location -r (Join-Path $Root "setup\requirements-wizard.txt") *>> $Log
    if ($LASTEXITCODE -ne 0) { Fail "Sihirbaz bileşenleri kurulamadı." }
    Info "✓"

    Step 6 "Kurulum sihirbazı açılıyor…"
    Info "Tarayıcıda açılacak. Bu pencereyi kurulum bitene kadar kapatmayın."
    Push-Location $Root
    & $Py -m setup.wizard @WizardArgs
    $code = $LASTEXITCODE
    Pop-Location
    exit $code
} catch {
    Fail $_.Exception.Message
}
