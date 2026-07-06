<#
.SYNOPSIS
    Watcher de la cua de PROJECCIONS d'opens del PWA. Consulta Supabase
    (fcbillar.open_projection_requests) i, si hi ha peticions pendents, genera
    l'open projectat en LOCAL amb `fcbillar project-open-ranking`.

.DESCRIPTION
    El botó "Genera open des del rànquing inicial" (web/PWA, admin-gated)
    insereix una fila a fcbillar.open_projection_requests amb el PDF 'RÀNQUING
    INICIAL' en base64. La generació ha de córrer EN LOCAL (reusa el motor Python
    i resol els fcb_id contra la BD), així que aquest watcher fa de pont:

      1. GET peticions pendents (status=pending) amb la service_role (només
         metadades; el base64 es baixa quan es processa cada fila).
      2. Tallafoc diari LOCAL (mai més de $MaxPerDay generacions/dia).
      3. Per cada pendent: la RECLAMA (status=running), baixa el base64, el desa
         a un .pdf temporal, executa `fcbillar project-open-ranking … --json`,
         i la marca 'done'/'error' amb el resum (buidant el base64 per no ocupar).

    Aïllat expressament de reingest_watcher.ps1 per no tocar el flux de reingesta
    (el del "bucle desbocat"). Compatible amb Windows PowerShell 5.1.
    Pensat per a la Tasca Programada de Windows (cada pocs minuts).

.PARAMETER MaxPerDay
    Màxim de generacions disparades pel botó en un dia (anti-abús). Per defecte 20.

.PARAMETER DryRun
    Detecta i informa, però no genera res ni toca estats.
#>
param(
    [int]$MaxPerDay = 20,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$wlog = Join-Path $logDir 'open_projection_watcher.log'
function Write-WLog($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -LiteralPath $wlog -Value $line
}

# --- Carrega SUPABASE_URL / SERVICE_ROLE_KEY del .env -----------------------
function Import-DotEnvKeys($path, [string[]]$keys) {
    $out = @{}
    if (-not (Test-Path $path)) { return $out }
    foreach ($raw in Get-Content -LiteralPath $path) {
        $t = $raw.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $eq = $t.IndexOf('=')
        if ($eq -lt 1) { continue }
        $name = $t.Substring(0, $eq).Trim()
        if ($keys -notcontains $name) { continue }
        $out[$name] = $t.Substring($eq + 1).Trim().Trim('"').Trim("'")
    }
    return $out
}
$cfg = Import-DotEnvKeys (Join-Path $repo '.env') @('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY')
$sbUrl = $cfg['SUPABASE_URL']
$sbKey = $cfg['SUPABASE_SERVICE_ROLE_KEY']
if (-not $sbUrl -or -not $sbKey) {
    Write-WLog "ERROR: falten SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY al .env. Avortant."
    exit 1
}

$rest = "$($sbUrl.TrimEnd('/'))/rest/v1/open_projection_requests"
$hRead = @{ apikey = $sbKey; Authorization = "Bearer $sbKey"; 'Accept-Profile' = 'fcbillar' }
$hWrite = @{ apikey = $sbKey; Authorization = "Bearer $sbKey"; 'Content-Profile' = 'fcbillar'; 'Content-Type' = 'application/json'; Prefer = 'return=minimal' }
function NowIso { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }

# --- 1) Peticions pendents (només metadades) --------------------------------
try {
    $pending = @(Invoke-RestMethod -Method Get -Headers $hRead `
            -Uri "$rest`?status=eq.pending&select=id,requested_at,season,file_name&order=requested_at.asc")
} catch {
    Write-WLog "ERROR consultant pendents: $_"
    exit 1
}
# Només files amb 'id' real (un objecte d'error de PostgREST retornat amb 200 no
# ha de comptar com a pendent — vegeu el bucle desbocat de reingest_watcher).
$pending = @($pending | Where-Object { $_.id })
if ($pending.Count -eq 0) { exit 0 }   # res a fer (cas normal, silenciós)

Write-WLog "$($pending.Count) petici(ons) de projecció pendents."

# --- 2) Tallafoc diari LOCAL ------------------------------------------------
$fireFile = Join-Path $repo 'data\.open_projection_fires.json'
$today = (Get-Date).ToString('yyyy-MM-dd')
$fires = $null
if (Test-Path $fireFile) {
    try { $fires = Get-Content -LiteralPath $fireFile -Raw | ConvertFrom-Json } catch { $fires = $null }
}
if (-not $fires) { $fires = [pscustomobject]@{ date = $today; count = 0 } }
if ($fires.date -ne $today) { $fires.date = $today; $fires.count = 0 }

if ([int]$fires.count -ge $MaxPerDay) {
    Write-WLog ("TALLAFOC: ja s'han generat {0} projeccions avui (màx {1}). Deixo {2} pendent(s) a la cua." -f [int]$fires.count, $MaxPerDay, $pending.Count)
    exit 0
}

if ($DryRun) {
    Write-WLog ("DryRun: {0} pendent(s): {1}" -f $pending.Count, (($pending | ForEach-Object { $_.file_name }) -join ', '))
    exit 0
}

# --- 3) Processa cada pendent (reclamar → generar → marcar) -----------------
$tmpDir = Join-Path $env:TEMP 'fcb_open_proj'
New-Item -ItemType Directory -Force $tmpDir | Out-Null

foreach ($p in $pending) {
    if ([int]$fires.count -ge $MaxPerDay) {
        Write-WLog ("TALLAFOC diari assolit ({0}); deixo la resta a la cua." -f $MaxPerDay)
        break
    }
    $id = $p.id
    $season = $p.season

    # Reclamar (running) ABANS d'executar: si el PATCH falla, no processem (evita
    # re-tret al cicle següent). Un tret no reclamable s'omet.
    try {
        Invoke-RestMethod -Method Patch -Headers $hWrite -Uri "$rest`?id=eq.$id" `
            -Body (@{ status = 'running'; started_at = (NowIso) } | ConvertTo-Json) | Out-Null
    } catch {
        Write-WLog "No he pogut reclamar $id ($_). L'ometo."
        continue
    }
    $fires.count = [int]$fires.count + 1
    try { $fires | ConvertTo-Json | Set-Content -LiteralPath $fireFile -Encoding UTF8 } catch {}

    $status = 'error'; $message = ''; $summary = $null
    $tmpPdf = Join-Path $tmpDir ("proj_{0}.pdf" -f $id)
    try {
        # Baixa el base64 només ara (evita transferir-lo al poll).
        $row = @(Invoke-RestMethod -Method Get -Headers $hRead -Uri "$rest`?id=eq.$id&select=pdf_base64,season")
        $b64 = if ($row.Count) { $row[0].pdf_base64 } else { $null }
        if (-not $b64) { throw "sense pdf_base64" }
        [IO.File]::WriteAllBytes($tmpPdf, [Convert]::FromBase64String($b64))

        $cliArgs = @('run', 'fcbillar', 'project-open-ranking', $tmpPdf, '--json')
        if ($season) { $cliArgs += @('--season', $season) }
        Write-WLog ("Generant projecció per {0} ({1})…" -f $id, $p.file_name)
        $output = (& uv @cliArgs 2>&1 | Out-String)
        $code = $LASTEXITCODE
        $message = (($output -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 4) -join ' | ').Trim()
        if ($code -eq 0) {
            $status = 'done'
            $jsonLine = ($output -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
            if ($jsonLine) { try { $summary = $jsonLine | ConvertFrom-Json } catch {} }
        }
    } catch {
        $message = "$_"
        Write-WLog "ERROR generant $id : $_"
    } finally {
        if (Test-Path $tmpPdf) { Remove-Item -LiteralPath $tmpPdf -Force -ErrorAction SilentlyContinue }
    }

    # Marca l'estat final i BUIDA el base64 (per no ocupar espai a la taula).
    $patch = @{ status = $status; finished_at = (NowIso); pdf_base64 = ''; message = $message }
    if ($summary) {
        $patch.division_id = $summary.division_id
        $patch.open_name = $summary.open_name
        $patch.n_players = $summary.n_players
    }
    try {
        Invoke-RestMethod -Method Patch -Headers $hWrite -Uri "$rest`?id=eq.$id" -Body ($patch | ConvertTo-Json) | Out-Null
    } catch { Write-WLog "AVÍS: no he pogut marcar '$status' per $id : $_" }
    Write-WLog ("Petició {0}: {1}." -f $id, $status)
}

# Manté el log acotat (últimes 500 línies).
$lines = Get-Content -LiteralPath $wlog -ErrorAction SilentlyContinue
if ($lines.Count -gt 500) { Set-Content -LiteralPath $wlog -Value ($lines | Select-Object -Last 500) }

exit 0
