# Organizador de Arquivos ACME — versão 0.2

Aplicativo desktop para Windows que encontra **duplicados exatos** com SHA-256 e **organiza arquivos**
por tipo, por período ou por regras, sempre com prévia, confirmação, histórico e Desfazer.
Nenhum arquivo é excluído ou sobrescrito.

## O que esta versão faz

- Seleção de pasta com bloqueio de pastas do sistema (Windows, Program Files, AppData) e da raiz de unidades.
- Varredura de arquivos e subpastas sem seguir links simbólicos ou junções.
- Detecção de duplicados exatos em etapas: tamanho → SHA-256 dos primeiros 64 KB → SHA-256 completo (blocos de 1 MB) → comparação byte a byte opcional.
- Arquivos do OneDrive disponíveis somente na nuvem **não são lidos** (para não forçar download) e aparecem em "Não analisados".
- Arquivos bloqueados, sem permissão ou alterados durante a análise são registrados com o motivo, sem interromper a análise.
- Indicadores reais: total de arquivos e pastas, duplicados exatos, espaço potencialmente recuperável, não analisados, tempo de análise.
- Abas: duplicados exatos (grupos), arquivos por categoria, não analisados.
- Exportação do relatório em CSV (abre no Excel), sem sobrescrever arquivo existente.
- Análise em segundo plano com botão Cancelar.

"Espaço potencialmente recuperável" = tamanho × (cópias − 1). Nada é liberado de fato nesta versão.

## Organizar (novo na 0.2)

- Modos: por tipo de arquivo (PDFs, Excel, Word...), por período (Ano / "10 - Outubro", pela data de modificação ou criação) e por regras personalizadas ("Admissão" → RH/Admissões). Regras ignoram maiúsculas e acentos e ficam salvas.
- Por padrão organiza só os arquivos soltos na pasta escolhida; "Incluir arquivos das subpastas" é opcional.
- A prévia mostra cada arquivo, o local atual e o novo local. Mudar qualquer opção descarta a prévia: só se confirma o que foi visto.
- Segurança na execução: nada é excluído; se já existe um arquivo com o mesmo nome no destino, o novo recebe "(2)"; origem e destino precisam estar dentro da pasta escolhida; arquivo alterado depois da prévia não é movido; arquivo em uso (aberto no Excel, por exemplo) é pulado com o motivo.
- Aviso antes de confirmar quando a pasta é de rede, biblioteca do SharePoint/Teams ou OneDrive compartilhável.
- Histórico em `%LOCALAPPDATA%\organizador_acme\historico.db` (SQLite): data, usuário, máquina, origem, destino, categoria, situação e erro de cada arquivo. O plano é gravado antes do primeiro movimento, então uma queda no meio pode ser desfeita.
- Desfazer devolve cada arquivo ao local original, exceto se ele foi modificado depois (tamanho ou data diferentes) ou se o local original está ocupado. Pastas criadas pela organização são removidas se ficarem vazias.

## Como usar

Abra `programa\OrganizadorACME\OrganizadorACME.exe` (ou o atalho na Área de Trabalho). Não precisa de terminal.

## Gerar o executável de novo (depois de mudar o código)

No PowerShell, dentro desta pasta: `.\gerar_executavel.ps1`

Na primeira vez ele cria o ambiente Python em `%LOCALAPPDATA%\organizador_acme\venv` (sem administrador).
Os testes rodam antes; se algum falhar, nada é gerado. O build é feito fora do OneDrive e copiado para `programa\OrganizadorACME`.
Mesmo padrão do AutomacoesACME.

## Instalador para os colaboradores

No PowerShell, dentro desta pasta: `.\gerar_instalador.ps1`. Ele roda o `gerar_executavel.ps1` (testes + executável) e gera
`instalador\saida\Instalar_OrganizadorACME_<versão>.exe` (precisa do Inno Setup 6, instalado com "Install for me only").

- O colaborador instala sem administrador, em `%LOCALAPPDATA%\Programs\OrganizadorACME`, com atalho no menu Iniciar (pasta ACME)
  e atalho opcional na Área de Trabalho.
- Desinstala pelo Painel de Controle (Programas e Recursos / Aplicativos instalados).
- Instalar uma versão nova por cima atualiza o programa e mantém o histórico (`%LOCALAPPDATA%\organizador_acme`).
- Sem assinatura digital da TI, o SmartScreen pode avisar: clique em "Mais informações" > "Executar assim mesmo".

## Desenvolver no VS Code

Abra esta pasta no VS Code, aceite as extensões recomendadas (Python, Pylance, Ruff) e pressione **F5**.
O VS Code usa o mesmo ambiente criado pelo `gerar_executavel.ps1`.

## Estrutura

```
lancador_app.py            ponto de entrada do OrganizadorACME.exe
gerar_executavel.ps1       gera o executável em programa\OrganizadorACME
ferramentas/gerar_icone.py gera recursos\icone.ico nas cores ACME
acme/core/paths.py        validação de pastas, atributos do OneDrive, caminhos longos
acme/core/scanner.py      varredura somente leitura
acme/core/duplicates.py   detector SHA-256
acme/core/categories.py   categorias por extensão
acme/core/report.py       exportação CSV e formatação
acme/core/planner.py      prévia da organização (não move nada)
acme/core/executor.py     execução segura e Desfazer (única parte que move arquivos)
acme/core/history.py      histórico em SQLite
acme/ui/                  interface PySide6 (janela, tema, worker em segundo plano)
tests/                     testes automatizados (pytest)
```

O núcleo (`acme/core`) não depende da interface e pode ser testado isoladamente.

## Testes automatizados (48)

Duplicados: pasta vazia, nomes diferentes com conteúdo idêntico, mesmo nome com conteúdo diferente, mesmo tamanho com hash diferente,
arquivo grande que difere no último byte, modo byte a byte, colisão simulada, vazios, originais preservados, caracteres especiais,
caminhos longos, arquivo bloqueado, somente na nuvem, links, cancelamento, 3.000 arquivos, pastas protegidas, CSV.
Organização: prévia não move nada, os três modos, destinos de regra fora da pasta recusados, subpastas, conflito de nome,
dois arquivos para o mesmo destino, arquivo criado no destino depois da prévia, arquivo alterado depois da prévia, arquivo em uso,
histórico, Desfazer completo, Desfazer com arquivo modificado, Desfazer com local ocupado, cancelamento no meio,
queda entre mover e gravar, nunca exclui conteúdo. Interface: análise, prévia → confirmação → Desfazer, pasta protegida.

## Próximas fases

Arquivos semelhantes e versões → classificação por assunto → instalador.
