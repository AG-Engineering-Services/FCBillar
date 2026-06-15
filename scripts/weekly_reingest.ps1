<#
.SYNOPSIS
    Reingesta setmanal completa de FCBillar (partides + rànquings) i publicació
    al núvol. Pensat per executar-se DESATÈS via Tasca Programada de Windows la
    nit de diumenge a dilluns (dilluns 03:00).

.DESCRIPTION
    Incorpora les darreres novetats publicades al web de la federació
    (fcbillar.cat) durant el cap de setmana i les puja a Supabase, d'on l'app
    web (Vercel) les llegeix en temps d'execució (no cal re-desplegar).

    Passos (cadascun aïllat; si un falla, p.ex. la sessió de login ha caducat,
    la resta continua i s'apunta al log):

      INGESTA LOCAL  ->  data/fcbillar.db i data/fcb_opens.db
        1. fcbillar import-temporada       clubs + rànquings per modalitat   [LOGIN]
        2. fcbillar ingest-individuals     opens / torneigs individuals
        3. fcbillar ingest-copa <edicio>   Copa Catalana
        4. fcb_opens scrape-current-opens  opens (BD fcb_opens)
        5. fcb_opens scrape-lliga 36 --full lliga Tres Bandes (BD fcb_opens)

      PUBLICACIÓ NÚVOL  ->  Supabase (schemes fcbillar + fcb_opens)
        6. fcbillar publish-cloud          rànquings/partides/lliga/copa/opens(+femení)
        7. fcb_opens supabase-sync         BD d'opens

    FINESTRA DE TEMPORADA: actiu del 25 d'agost al 31 de juliol. Durant l'aturada
    d'estiu (1-24 d'agost) el job s'omet immediatament. Força'l amb -Force.

    CREDENCIALS: les claus SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY es carreguen
    de .env i s'injecten a l'entorn (fcb_opens NOMÉS llegeix l'entorn, no .env).

.PARAMETER CopaEdicio
    ID d'edició de la Copa a fcbillar.cat. ACTUALITZA aquest valor cada temporada.

.PARAMETER Force
    Executa encara que sigui dins l'aturada d'estiu (1-24 d'agost).

.PARAMETER DryRun
    Només mostra les comandes que executaria, sense fer-les.

.PARAMETER SkipPublish
    Fa la ingesta local però no publica al núvol (per a proves).
#>
param(
    [int]$CopaEdicio = 7,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$SkipPublish
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# --- Log amb marca de temps -------------------------------------------------
$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("reingest_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    Add-Content -LiteralPath $log -Value $line
}

# --- Porta de finestra de temporada (actiu 25-ago .. 31-jul) ---------------
$now = Get-Date
if (-not $Force -and $now.Month -eq 8 -and $now.Day -lt 25) {
    Write-Log "Aturada d'estiu (1-24 d'agost): fora de finestra de temporada. Ometent. (Usa -Force per forçar.)"
    exit 0
}

# --- uv robust a la PATH desatesa ------------------------------------------
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $cand = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path $cand) { $uv = $cand }
}
if (-not $uv) {
    Write-Log "ERROR: no s'ha trobat 'uv' a la PATH ni a ~/.local/bin. Avortant."
    exit 1
}

# --- Carrega SUPABASE_* del .env a l'entorn (fcb_opens només llegeix entorn) -
function Import-DotEnvKeys($path, [string[]]$keys) {
    if (-not (Test-Path $path)) { return }
    foreach ($raw in Get-Content -LiteralPath $path) {
        $t = $raw.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $eq = $t.IndexOf('=')
        if ($eq -lt 1) { continue }
        $name = $t.Substring(0, $eq).Trim()
        if ($keys -notcontains $name) { continue }
        $val = $t.Substring($eq + 1).Trim().Trim('"').Trim("'")
        if ($val) { Set-Item -Path ("Env:{0}" -f $name) -Value $val }
    }
}
Import-DotEnvKeys (Join-Path $repo '.env') @('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY')

# --- Executor de passos (aïllat; continua si un falla) ----------------------
$script:nOk = 0; $script:nFail = 0
function Invoke-Step($name, [string[]]$cmd) {
    Write-Log "=== $name ==="
    Write-Log ("  > " + ($cmd -join ' '))
    if ($DryRun) { return }
    try {
        & $cmd[0] @($cmd[1..($cmd.Count - 1)]) 2>&1 | ForEach-Object { Add-Content -LiteralPath $log -Value ("    " + $_) }
        $code = $LASTEXITCODE
        Write-Log "  exit=$code"
        if ($code -eq 0) { $script:nOk++ } else { $script:nFail++ }
    } catch {
        Write-Log "  ERROR: $_"
        $script:nFail++
    }
}

$haveKeys = $env:SUPABASE_URL -and $env:SUPABASE_SERVICE_ROLE_KEY
Write-Log "Inici reingesta setmanal (repo=$repo, copa=$CopaEdicio, dryrun=$DryRun, skipPublish=$SkipPublish, supabaseKeys=$([bool]$haveKeys))"

# --- INGESTA LOCAL ----------------------------------------------------------
Invoke-Step 'import-temporada (clubs + rànquings per modalitat) [LOGIN]' @($uv, 'run', 'fcbillar', 'import-temporada')
Invoke-Step 'ingest-individuals (opens / torneigs individuals)'          @($uv, 'run', 'fcbillar', 'ingest-individuals')
Invoke-Step 'ingest-copa'                                                @($uv, 'run', 'fcbillar', 'ingest-copa', "$CopaEdicio")
Invoke-Step 'fcb_opens scrape-current-opens'                             @($uv, 'run', 'python', '-m', 'fcb_opens.cli', 'scrape-current-opens')
Invoke-Step 'fcb_opens scrape-lliga 36 (--full)'                         @($uv, 'run', 'python', '-m', 'fcb_opens.cli', 'scrape-lliga', '36', '--full')

# --- PUBLICACIÓ AL NÚVOL ----------------------------------------------------
if ($SkipPublish) {
    Write-Log "SkipPublish actiu: no es publica al núvol."
} elseif (-not $haveKeys -and -not $DryRun) {
    Write-Log "AVÍS: falten SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY al .env. S'omet la publicació."
    $script:nFail++
} else {
    Invoke-Step 'fcbillar publish-cloud (Supabase fcbillar)'      @($uv, 'run', 'fcbillar', 'publish-cloud')
    Invoke-Step 'fcb_opens supabase-sync (Supabase fcb_opens)'    @($uv, 'run', 'python', '-m', 'fcb_opens.cli', 'supabase-sync')
}

# --- Neteja de logs antics (conserva els 30 més recents) --------------------
Get-ChildItem -LiteralPath $logDir -Filter 'reingest_*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Log "Fi reingesta. Passos OK=$($script:nOk) FALLATS=$($script:nFail). Log: $log"
exit $script:nFail
