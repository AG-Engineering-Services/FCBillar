<#
.SYNOPSIS
    Registra (o esborra) la Tasca Programada que executa el watcher de la cua de
    reingesta del botó del PWA cada pocs minuts.

.DESCRIPTION
    Crea la tasca "FCBillar - Watcher reingesta" que llança
    scripts\reingest_watcher.ps1 cada $EveryMin minuts, tot el dia. El watcher és
    lleuger (un GET a Supabase); només dispara la reingesta si hi ha peticions
    pendents a fcbillar.reingest_requests. Així el botó de la fitxa funciona en
    qualsevol moment (amb el PC engegat), no només els caps de setmana.

.PARAMETER EveryMin
    Interval de sondeig en minuts (per defecte 5).

.PARAMETER Unregister
    Esborra la tasca en comptes de crear-la.

.PARAMETER RunNow
    Després de registrar-la, la llança immediatament una vegada (prova).
#>
param(
    [int]$EveryMin = 5,
    [switch]$Unregister,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
$taskName = 'FCBillar - Watcher reingesta'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\reingest_watcher.ps1'

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tasca '$taskName' esborrada." -ForegroundColor Yellow
    return
}

if (-not (Test-Path $script)) { throw "No es troba $script" }

$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$action = New-ScheduledTaskAction -Execute $ps `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $script) `
    -WorkingDirectory $repo

# Trigger diari a les 00:00 que es repeteix cada $EveryMin minuts tot el dia
# (es re-arma cada dia). Patró robust a Windows PowerShell 5.1.
$trigger = New-ScheduledTaskTrigger -Daily -At '00:00'
$rep = (New-ScheduledTaskTrigger -Once -At '00:00' `
        -RepetitionInterval (New-TimeSpan -Minutes $EveryMin) `
        -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType Interactive -RunLevel Limited

$task = New-ScheduledTask -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Sondeja la cua fcbillar.reingest_requests cada $EveryMin min i dispara la reingesta quan el botó del PWA (fitxa Albert Gómez) ho demana."

try {
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
    Write-Host "Tasca '$taskName' registrada: cada $EveryMin min." -ForegroundColor Green
} catch {
    Write-Host "ERROR registrant la tasca: $_" -ForegroundColor Red
    Write-Host "Si és 'Accés denegat', obre PowerShell com a Administrador i torna-ho a executar." -ForegroundColor Yellow
    throw
}

Get-ScheduledTask -TaskName $taskName |
    Select-Object TaskName, State, @{n = 'NextRun'; e = { (Get-ScheduledTaskInfo $_.TaskName).NextRunTime } } |
    Format-List

if ($RunNow) {
    Write-Host "Llançant el watcher ara (prova)..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $taskName
}
