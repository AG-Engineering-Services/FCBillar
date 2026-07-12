<#
.SYNOPSIS
    Desplega el frontend (web/) a Vercel (projecte seguiment-lliga-open).

.DESCRIPTION
    NOTA (juny 2026): el projecte de Vercel ja està connectat per Git al repo
    FCBillar (Root Directory = web, branca master), de manera que cada push a
    master desplega SOL. Aquest script queda com a ALTERNATIVA MANUAL (per
    publicar a l'instant sense passar per un push, o si l'auto-deploy falla).

    Com que Vercel adjunta les metadades Git del repo on s'executa, aquest
    script copia el codi font de web/ a una carpeta temporal FORA de cap repo
    Git i desplega des d'allà per evitar conflictes de metadades.

    Requisits: `vercel login` amb el compte que té "Albert's projects".
    Les env vars (PUBLIC_SUPABASE_URL / PUBLIC_SUPABASE_ANON_KEY) ja són al
    projecte de Vercel; el build les injecta.
#>
param([switch]$Preview)

$ErrorActionPreference = 'Stop'
$web = $PSScriptRoot
$tmp = Join-Path $env:TEMP ("fcbweb_deploy_{0}" -f (Get-Random))
# El projecte Vercel té Root Directory = 'web', així que l'app ha de quedar sota
# un subdir web/ (si es copia a l'arrel, Vercel busca .../web i falla). El
# .vercel/project.json va a l'arrel del temp (el CLI el llegeix des d'allà).
$dst = Join-Path $tmp 'web'
$scope = 'alberts-projects-92d169cf'

New-Item -ItemType Directory -Force -Path "$dst\src", "$tmp\.vercel" | Out-Null
foreach ($f in 'package.json','svelte.config.js','vite.config.ts','tailwind.config.js','postcss.config.js','tsconfig.json','.gitignore') {
    Copy-Item (Join-Path $web $f) (Join-Path $dst $f) -Force
}
Copy-Item (Join-Path $web 'src\*') (Join-Path $dst 'src') -Recurse -Force
if (Test-Path (Join-Path $web 'static')) { Copy-Item (Join-Path $web 'static') $dst -Recurse -Force }
Copy-Item (Join-Path $web '.vercel\project.json') (Join-Path $tmp '.vercel\project.json') -Force

Push-Location $tmp
try {
    $prod = if ($Preview) { '' } else { '--prod' }
    Write-Host "Desplegant des de $tmp ..." -ForegroundColor Cyan
    & vercel deploy $prod --yes --scope $scope
} finally {
    Pop-Location
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
