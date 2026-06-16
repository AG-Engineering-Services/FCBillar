<#
.SYNOPSIS
    Registra (o esborra) la Tasca Programada de Windows que executa la reingesta
    setmanal de FCBillar la nit de diumenge a dilluns.

.DESCRIPTION
    Crea una tasca que llança scripts\weekly_reingest.ps1 DIVENDRES, DISSABTE i
    DIUMENGE a les 22:30 (per capturar els games del cap de setmana a mesura que
    es disputen) i DILLUNS a les 03:00 (repàs), com l'usuari actual. Opcions clau:
      - StartWhenAvailable: si l'equip estava apagat a les 03:00, s'executa tan
        aviat com torni a estar disponible (catch-up del cap de setmana).
      - WakeToRun: desperta l'equip si està en suspensió.
      - La finestra de temporada (25-ago .. 31-jul) la gestiona el propi script.

    La tasca corre amb LogonType Interactive (l'usuari ha d'estar amb sessió
    iniciada; la pantalla pot estar bloquejada). Si la vols "tant si hi ha sessió
    com si no", caldrà -RunLevel/-LogonType S4U i privilegis d'administrador.

.PARAMETER At
    Hora d'inici (per defecte 03:00).

.PARAMETER Unregister
    Esborra la tasca en comptes de crear-la.

.PARAMETER RunNow
    Després de registrar-la, la llança immediatament una vegada (prova).
#>
param(
    [string]$At = '03:00',
    [string]$Weekend = '22:30',
    [switch]$Unregister,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
$taskName = 'FCBillar - Reingesta setmanal'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'scripts\weekly_reingest.ps1'

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tasca '$taskName' esborrada." -ForegroundColor Yellow
    return
}

if (-not (Test-Path $script)) { throw "No es troba $script" }

# Windows PowerShell 5.1 sempre present; l'script és compatible.
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$action = New-ScheduledTaskAction -Execute $ps `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $script) `
    -WorkingDirectory $repo

# Cap de setmana de competició: divendres/dissabte/diumenge a la nit (22:30) per
# capturar els games a mesura que es disputen, + el repàs de dilluns (03:00).
$triggers = @(
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday, Saturday, Sunday -At $Weekend
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $At
)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType Interactive -RunLevel Limited

$task = New-ScheduledTask -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal `
    -Description 'Reingesta completa de partides i rànquings de FCBillar i publicació a Supabase. Finestra de temporada 25-ago..31-jul (gestionada per weekly_reingest.ps1). Divendres/dissabte/diumenge a la nit + repàs de dilluns.'

try {
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
    Write-Host "Tasca '$taskName' registrada: Dv/Ds/Dg a les $Weekend + Dl a les $At." -ForegroundColor Green
} catch {
    Write-Host "ERROR registrant la tasca: $_" -ForegroundColor Red
    Write-Host "Si és 'Accés denegat', obre PowerShell com a Administrador i torna-ho a executar." -ForegroundColor Yellow
    throw
}

# Mostra el resum
Get-ScheduledTask -TaskName $taskName |
    Select-Object TaskName, State, @{n = 'NextRun'; e = { (Get-ScheduledTaskInfo $_.TaskName).NextRunTime } } |
    Format-List

if ($RunNow) {
    Write-Host "Llançant la tasca ara (prova)..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $taskName
}
