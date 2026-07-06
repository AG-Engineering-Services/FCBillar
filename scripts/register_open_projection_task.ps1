<#
.SYNOPSIS
    Registra (o esborra) la Tasca Programada que executa el watcher de la cua de
    PROJECCIONS d'opens del PWA cada pocs minuts.

.DESCRIPTION
    Crea la tasca "FCBillar - Watcher projeccions opens" que llança
    scripts\open_projection_watcher.ps1 cada $EveryMin minuts, tot el dia. És
    lleuger (un GET a Supabase); només genera si hi ha peticions pendents a
    fcbillar.open_projection_requests (botó "Genera open des del rànquing inicial"
    del PWA). Independent del watcher de reingesta.

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
$taskName = 'FCBillar - Watcher projeccions opens'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\open_projection_watcher.ps1'

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

# Trigger diari a les 00:00 que es repeteix cada $EveryMin minuts tot el dia.
$trigger = New-ScheduledTaskTrigger -Daily -At '00:00'
$rep = (New-ScheduledTaskTrigger -Once -At '00:00' `
        -RepetitionInterval (New-TimeSpan -Minutes $EveryMin) `
        -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType Interactive -RunLevel Limited

$task = New-ScheduledTask -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Sondeja la cua fcbillar.open_projection_requests cada $EveryMin min i genera l'open projectat quan el botó del PWA ho demana."

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
