<#
  Gera o instalador para os colaboradores em instalador\saida\Instalar_OrganizadorACME_<versão>.exe.
    .\gerar_instalador.ps1
  Roda antes o gerar_executavel.ps1 (testes + executável); se falhar, nada é gerado.
  Precisa do Inno Setup 6 (jrsoftware.org, "Install for me only").
#>
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot 'gerar_executavel.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'gerar_executavel.ps1 falhou; instalador não gerado.' }
    $linha = Select-String -Path 'acme\__init__.py' -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $linha) { throw 'Versão não encontrada em acme\__init__.py.' }
    $versao = $linha.Matches[0].Groups[1].Value
    $locais = @((Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6'), (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6'))
    $iscc = $locais | ForEach-Object { Join-Path $_ 'ISCC.exe' } | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 não encontrado. Instale de https://jrsoftware.org/isdl.php escolhendo "Install for me only" (não precisa de administrador).' }
    & $iscc "/DAppVersion=$versao" 'instalador\OrganizadorACME.iss'
    if ($LASTEXITCODE -ne 0) { throw "ISCC falhou (código $LASTEXITCODE)." }
    Write-Host "Instalador: $PSScriptRoot\instalador\saida\Instalar_OrganizadorACME_$versao.exe" -ForegroundColor Green
} finally { Pop-Location }
