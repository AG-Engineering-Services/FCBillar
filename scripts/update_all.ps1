<#
.SYNOPSIS
    Actualització automàtica de dades de FCBillar (rànquings, lliga, copa, opens).

.DESCRIPTION
    Pensat per executar-se desatès (Tasca programada de Windows) divendres,
    dissabte i diumenge a la nit. Executa cada pas per separat i registra la
    sortida amb marca de temps a data\logs\, de manera que si un pas falla
    (p.ex. cal tornar a iniciar sessió a fcbillar.cat) la resta continua.

    Passos:
      1. fcbillar import-temporada   -> clubs + sincronització de rànquings (requereix sessió)
      2. fcbillar ingest-individuals -> opens / torneigs individuals
      3. fcbillar ingest-copa        -> Copa Catalana (edició configurable)
      4. fcb_opens scrape-current-opens -> opens (BD fcb_opens)
      5. fcb_opens scrape-lliga 36 --full -> lliga Tres Bandes (BD fcb_opens)

.PARAMETER CopaEdicio
    ID d'edició de la Copa a fcbillar.cat. ACTUALITZA aquest valor cada temporada.

.PARAMETER DryRun
    Només mostra les comandes que executaria, sense fer-les.
#>
param(
    [int]$CopaEdicio = 7,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("update_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg
    Write-Output $line
    Add-Content -LiteralPath $log -Value $line
}

function Invoke-Step($name, [string[]]$cmd) {
    Write-Log "=== $name ==="
    Write-Log ("  > " + ($cmd -join ' '))
    if ($DryRun) { return }
    try {
        & $cmd[0] @($cmd[1..($cmd.Count - 1)]) 2>&1 | ForEach-Object { Add-Content -LiteralPath $log -Value $_ }
        Write-Log "  exit=$LASTEXITCODE"
    } catch {
        Write-Log "  ERROR: $_"
    }
}

Write-Log "Inici actualització (repo=$repo, copa edició=$CopaEdicio, dryrun=$DryRun)"

Invoke-Step 'login automàtic (captcha OCR)'             @('uv','run','fcbillar','login','--auto')
Invoke-Step 'import-temporada (clubs + sync rànquings)' @('uv','run','fcbillar','import-temporada')
Invoke-Step 'ingest-individuals (opens)'                @('uv','run','fcbillar','ingest-individuals')
Invoke-Step 'ingest-copa'                               @('uv','run','fcbillar','ingest-copa',"$CopaEdicio")
Invoke-Step 'fcb_opens scrape-current-opens'            @('uv','run','python','-m','fcb_opens.cli','scrape-current-opens')
Invoke-Step 'fcb_opens scrape-lliga 36'                 @('uv','run','python','-m','fcb_opens.cli','scrape-lliga','36','--full')

Write-Log "Fi actualització. Log: $log"
