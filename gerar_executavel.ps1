<#
  Gera de novo o executável em programa\OrganizadorACME (depois de mudar o código).
    .\gerar_executavel.ps1
  Na primeira vez cria o ambiente Python em %LOCALAPPDATA%\organizador_acme\venv (não precisa de administrador).
  Os testes rodam antes; se algum falhar, nada é gerado.
  O build é feito fora do OneDrive (sem bloqueio de sincronização) e depois copiado.
#>
$ErrorActionPreference = 'Continue'  # PyInstaller escreve progresso no stderr; o resultado é conferido pelo código de saída
$base   = Join-Path $env:LOCALAPPDATA 'organizador_acme'
$python = Join-Path $base 'venv\Scripts\python.exe'
$build  = Join-Path $base 'build'
$dist   = Join-Path $base 'dist'
$nome   = 'OrganizadorACME'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path $python)) {
        Write-Host 'Criando o ambiente Python (só na primeira vez)...' -ForegroundColor Yellow
        & py -3 -m venv (Join-Path $base 'venv')
        if ($LASTEXITCODE -ne 0) { & python -m venv (Join-Path $base 'venv') }
        if (-not (Test-Path $python)) { throw 'Python não encontrado. Instale o Python 3.12+ (python.org, "Install for me only").' }
        & $python -m pip install --upgrade pip
    }
    & $python -m pip install -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências (requirements.txt).' }
    if (-not (Test-Path 'recursos\icone.ico')) { & $python ferramentas\gerar_icone.py }
    & $python -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Testes falharam; executável não gerado.' }
    $argumentos = @('--noconfirm', '--clean', '--windowed', '--name', $nome, '--distpath', $dist, '--workpath', $build,
        '--specpath', $build, '--collect-submodules', 'acme',
        '--add-data', ((Join-Path $PSScriptRoot 'recursos') + ';recursos'),
        '--icon', (Join-Path $PSScriptRoot 'recursos\icone.ico'), 'lancador_app.py')
    & $python -m PyInstaller @argumentos 2>$null
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (rode o comando sem 2>`$null para ver o erro)." }
    robocopy (Join-Path $dist $nome) (Join-Path $PSScriptRoot "programa\$nome") /MIR /R:5 /W:3 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar $nome (robocopy $LASTEXITCODE). Feche o programa e tente de novo." }
    Write-Host "Executável: $PSScriptRoot\programa\$nome\$nome.exe" -ForegroundColor Green
    $global:LASTEXITCODE = 0  # robocopy devolve 1 quando copiou arquivos, o que é sucesso
} finally { Pop-Location }
