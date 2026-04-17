# Monitor de oportunidades SOUGOV

Este projeto coleta as oportunidades exibidas em `Buscar Oportunidades` no SOUGOV usando Python + Playwright e gera uma base local mais facil de filtrar.

## O que ele faz

- reaproveita uma sessao autenticada salva em `output/playwright/sougov-auth.json`
- abre o portal, expande os cards recolhidos e extrai as oportunidades
- entra em cada `Ver detalhes da oportunidade` para enriquecer o dataset
- tenta baixar localmente o PDF de cada edital quando o portal disponibiliza o arquivo
- salva os resultados em JSON e CSV
- permite filtros locais por texto, orgao, programa de gestao e prazo
- oferece um painel local em Streamlit para explorar a base

## Preparacao

```powershell
1_preparar_ambiente.bat
```

Esse script:

- cria a virtualenv `.venv`
- atualiza o `pip`
- instala os pacotes do projeto
- instala o navegador `chromium` do Playwright

## Primeiro uso

Se o arquivo de autenticacao ainda nao existir ou estiver expirado:

```powershell
2_executar_solucao.bat
```

Depois escolha a opcao de scraping com novo login manual. O navegador vai abrir, voce conclui o login no GOV.BR e volta ao terminal para continuar.

Se o login no navegador aberto pelo scraper ficar instavel, use o modo mais robusto:

1. no menu de [2_executar_solucao.bat](D:\Desenvolvimento\GovBR\2_executar_solucao.bat), escolha `3 - Abrir Chrome manual para login no SOUGOV`
2. faça o login no SOUGOV nesse Chrome manual
3. depois volte ao menu e escolha `4 - Conectar ao Chrome manual ja autenticado`

Atalho prático:

- se preferir, escolha diretamente a opcao `4`
- se o Chrome manual ainda nao estiver aberto, o menu abre o Chrome para voce
- depois que o login estiver concluido, basta confirmar no terminal e o scraping continua

## Exemplos

Coleta completa:

```powershell
python scraper.py
```

Apenas vagas com texto relacionado a TI:

```powershell
python scraper.py --query TI --limite 20
```

Apenas oportunidades da CGU encerrando em ate 7 dias:

```powershell
python scraper.py --orgao CGU --encerrando-em-ate 7
```

Apenas programa parcial:

```powershell
python scraper.py --programa Parcial
```

Rodar uma prova mais rapida coletando detalhes so das 10 primeiras apos o filtro:

```powershell
python scraper.py --query TI --max-details 10 --limite 10
```

## Saidas

- JSON: `data/oportunidades.json`
- CSV: `data/oportunidades.csv`
- PDFs dos editais: `data/editais/`

## Painel local

Para abrir a interface local em Streamlit:

```powershell
2_executar_solucao.bat
```

Depois escolha a opcao de abrir o relatorio local.

O painel oferece:

- busca livre
- filtros por órgão, programa, local e vínculo
- recorte por prazo
- priorização por palavras-chave do seu perfil
- visualização em cards, tabela e insights
- acesso ao PDF local do edital, quando ele tiver sido baixado
- download do CSV já filtrado

## Atalhos no Windows

Os dois pontos de entrada principais agora sao:

- [1_preparar_ambiente.bat](D:\Desenvolvimento\GovBR\1_preparar_ambiente.bat): cria a virtualenv e instala tudo
- [2_executar_solucao.bat](D:\Desenvolvimento\GovBR\2_executar_solucao.bat): menu principal para scraping e relatorio

Fluxo sugerido no dia a dia:

1. Rodar [1_preparar_ambiente.bat](D:\Desenvolvimento\GovBR\1_preparar_ambiente.bat) uma vez.
2. No uso diário, rodar [2_executar_solucao.bat](D:\Desenvolvimento\GovBR\2_executar_solucao.bat).
3. Escolher `1` para atualizar a base normalmente.
4. Escolher `2` quando a sessão expirar.
5. Escolher `3` para abrir um Chrome manual pronto para login, quando precisar.
6. Escolher `4` para anexar ao Chrome manual ja autenticado.
7. Escolher `5` ou `6` para abrir o painel.
8. Escolher `7` para fazer `commit` e `push` e atualizar o Streamlit web com a base mais recente.

Os atalhos antigos continuam no projeto como utilitarios diretos:

- [atualizar_base.bat](D:\Desenvolvimento\GovBR\atualizar_base.bat)
- [atualizar_base_com_login.bat](D:\Desenvolvimento\GovBR\atualizar_base_com_login.bat)
- [abrir_painel.bat](D:\Desenvolvimento\GovBR\abrir_painel.bat)

## Observacoes

- O portal parece ser construído em OutSystems.
- A listagem principal observada em `2026-03-20` e carregada pela acao interna `Oportunidades/BuscarOportunidades/DataActionCarregar`.
- Como o login passa por autenticacao do GOV.BR, o caminho mais robusto continua sendo manter a autenticacao manual e reutilizar o `storage_state` salvo pelo Playwright.
