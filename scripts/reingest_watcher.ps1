<#
.SYNOPSIS
    Watcher de la cua de reingesta del PWA. Consulta Supabase
    (fcbillar.reingest_requests) i, si hi ha peticions pendents, executa
    scripts\weekly_reingest.ps1 al PC de casa.

.DESCRIPTION
    El botó "↻ Reingesta" de la fitxa de l'Albert Gómez (web/PWA) insereix una
    fila a fcbillar.reingest_requests amb la clau anon (gate per correu via RLS).
    La reingesta, però, ha de córrer EN LOCAL (necessita data\*.db i la sessió de
    login amb captcha), així que aquest watcher fa de pont:

      1. GET peticions pendents (status=pending) amb la service_role.
      2. Cooldown: si l'última reingesta va acabar fa < $CooldownMin minuts,
         deixa les pendents a la cua i surt (es llançaran al següent cicle lliure).
      3. Lock: si ja hi ha una reingesta en curs (data\.reingest.lock), surt.
      4. Marca les pendents com 'running', executa weekly_reingest.ps1 (síncron),
         i les marca 'done'/'error' amb el resultat.

    Pensat per executar-se cada pocs minuts via Tasca Programada de Windows
    (vegeu scripts\register_watcher_task.ps1). Compatible amb Windows PowerShell 5.1.

.PARAMETER CooldownMin
    Minuts mínims entre reingestes disparades pel botó (anti-abús). Per defecte 15.

.PARAMETER DryRun
    Detecta i informa, però no executa la reingesta ni toca estats.
#>
param(
    [int]$CooldownMin = 15,
    [int]$MaxPerDay = 4,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$wlog = Join-Path $logDir 'watcher.log'
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

$rest = "$($sbUrl.TrimEnd('/'))/rest/v1/reingest_requests"
$hRead = @{ apikey = $sbKey; Authorization = "Bearer $sbKey"; 'Accept-Profile' = 'fcbillar' }
$hWrite = @{ apikey = $sbKey; Authorization = "Bearer $sbKey"; 'Content-Profile' = 'fcbillar'; 'Content-Type' = 'application/json'; Prefer = 'return=minimal' }
function NowIso { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }

# --- 1) Peticions pendents --------------------------------------------------
try {
    $pending = @(Invoke-RestMethod -Method Get -Headers $hRead `
            -Uri "$rest`?status=eq.pending&select=id,requested_at,source&order=requested_at.asc")
} catch {
    Write-WLog "ERROR consultant pendents: $_"
    exit 1
}
# Només files amb 'id' real. Si la resposta no és un array de dades (p.ex. un
# objecte d'error de PostgREST retornat amb 200) es comptava com "1 pendent" amb
# id buit i disparava una reingesta FANTASMA cada cooldown: va ser el bucle
# desbocat del 2026-06-21 ("Disparant reingesta per 1 petició: " amb ids buits).
$pending = @($pending | Where-Object { $_.id })
if ($pending.Count -eq 0) { exit 0 }   # res a fer (cas normal, silenciós)

Write-WLog "$($pending.Count) petici(ons) pendents."

# --- 1b) TALLAFOC LOCAL (independent de l'estat a Supabase) -----------------
# El bucle desbocat del 2026-06-21 va venir de peticions que no sortien mai de
# 'pending' (re-inserció externa o PATCH d'estat fallit): cada cooldown es
# re-disparava una reingesta completa. Aquests dos guardes viuen en un fitxer
# LOCAL, així que acoten els trets encara que Supabase quedi inconsistent.
$fireFile = Join-Path $repo 'data\.reingest_watcher_fires.json'
$today = (Get-Date).ToString('yyyy-MM-dd')
$fires = $null
if (Test-Path $fireFile) {
    try { $fires = Get-Content -LiteralPath $fireFile -Raw | ConvertFrom-Json } catch { $fires = $null }
}
if (-not $fires) { $fires = [pscustomobject]@{ date = $today; count = 0; last = $null } }
if ($fires.date -ne $today) { $fires.date = $today; $fires.count = 0 }  # nou dia: reinicia comptador

# Cooldown LOCAL: si hem disparat fa < CooldownMin, no re-disparem.
if ($fires.last) {
    try {
        $sinceLocal = (New-TimeSpan -Start ([datetime]$fires.last).ToUniversalTime() -End (Get-Date).ToUniversalTime()).TotalMinutes
        if ($sinceLocal -lt $CooldownMin) {
            Write-WLog ("Cooldown LOCAL actiu (últim tret fa {0} min < {1}). Ometent." -f [int]$sinceLocal, $CooldownMin)
            exit 0
        }
    } catch {}
}
# Tallafoc diari: mai més de $MaxPerDay reingestes disparades pel botó en un dia.
if ([int]$fires.count -ge $MaxPerDay) {
    $srcs = (@($pending | ForEach-Object { $_.source }) | Sort-Object -Unique) -join ', '
    Write-WLog ("TALLAFOC: ja s'han disparat {0} reingestes avui (màx {1}). Deixo {2} pendent(s) [{3}] a la cua. Revisa qui insereix a reingest_requests." -f [int]$fires.count, $MaxPerDay, $pending.Count, $srcs)
    exit 0
}

# --- 2) Cooldown anti-abús (secundari; basat en l'estat de Supabase) --------
try {
    $lastDone = @(Invoke-RestMethod -Method Get -Headers $hRead `
            -Uri "$rest`?status=in.(done,error)&select=finished_at&order=finished_at.desc&limit=1")
} catch { $lastDone = @() }
if ($lastDone.Count -gt 0 -and $lastDone[0].finished_at) {
    $sinceMin = (New-TimeSpan -Start ([datetime]$lastDone[0].finished_at) -End (Get-Date).ToUniversalTime()).TotalMinutes
    if ($sinceMin -lt $CooldownMin) {
        Write-WLog ("Cooldown actiu (última fa {0} min < {1}). Deixo {2} pendent(s) a la cua." -f [int]$sinceMin, $CooldownMin, $pending.Count)
        exit 0
    }
}

# --- 3) Lock: ja hi ha una reingesta en curs? -------------------------------
$lockFile = Join-Path $repo 'data\.reingest.lock'
if (Test-Path $lockFile) {
    $ageMin = (New-TimeSpan -Start (Get-Item $lockFile).LastWriteTime -End (Get-Date)).TotalMinutes
    if ($ageMin -lt 180) {
        Write-WLog ("Reingesta ja en curs (lock fa {0} min). Reintentaré al següent cicle." -f [int]$ageMin)
        exit 0
    }
}

$ids = @($pending | ForEach-Object { $_.id })
$idList = ($ids -join ',')
Write-WLog ("Disparant reingesta per {0} petici(ons): {1}" -f $ids.Count, $idList)

if ($DryRun) { Write-WLog "DryRun: no executo res."; exit 0 }

# --- 4) Reclamar (running), executa, marca 'done'/'error' -------------------
# Reclamar és OBLIGATORI: si el PATCH a 'running' falla, NO executem, perquè no
# podríem garantir que les mateixes files no es re-disparin al cicle següent
# (era part del bucle desbocat). Un tret que no es pot reclamar s'avorta.
try {
    Invoke-RestMethod -Method Patch -Headers $hWrite -Uri "$rest`?id=in.($idList)" `
        -Body (@{ status = 'running'; started_at = (NowIso) } | ConvertTo-Json) | Out-Null
} catch {
    Write-WLog "ERROR: no he pogut marcar 'running' ($_). No executo per evitar re-tret."
    exit 1
}

# Registra el tret al fitxer LOCAL abans d'executar (compta per al tallafoc diari).
$fires.count = [int]$fires.count + 1
$fires.last = (Get-Date).ToUniversalTime().ToString('o')
try { $fires | ConvertTo-Json | Set-Content -LiteralPath $fireFile -Encoding UTF8 } catch {}

$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$script = Join-Path $repo 'scripts\weekly_reingest.ps1'
& $ps -NoProfile -ExecutionPolicy Bypass -File $script
$code = $LASTEXITCODE

$logName = (Get-ChildItem -LiteralPath $logDir -Filter 'reingest_*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
$status = if ($code -eq 0) { 'done' } else { 'error' }
$body = @{ status = $status; finished_at = (NowIso); n_fail = $code; message = $logName } | ConvertTo-Json
try {
    Invoke-RestMethod -Method Patch -Headers $hWrite -Uri "$rest`?id=in.($idList)" -Body $body | Out-Null
} catch { Write-WLog "AVÍS: no he pogut marcar '$status': $_" }

Write-WLog "Reingesta acabada (exit=$code, estat=$status, log=$logName)."

# Manté el watcher.log acotat (últimes 500 línies).
$lines = Get-Content -LiteralPath $wlog -ErrorAction SilentlyContinue
if ($lines.Count -gt 500) { Set-Content -LiteralPath $wlog -Value ($lines | Select-Object -Last 500) }

exit 0
