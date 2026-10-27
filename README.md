# Discord Bot

Este repositório contém **dois projetos separados**:

- **Bot principal:** continua na raiz (`bot.py`, `config.py`, `requirements.txt`). Esta migração não substitui nem altera o código dele.
- **Julinha Chan 1.8:** versão comunitária migrada para a pasta [`Julinha/`](Julinha/README.md).

## Executar o bot principal
Siga as instruções já existentes para o projeto da raiz. Não misture o ambiente virtual nem o arquivo `.env` com o projeto Julinha.

## Executar a Julinha
Entre na pasta `Julinha/` e siga o [README da Julinha](Julinha/README.md). Ela usa suas próprias dependências, configuração e banco de dados.

## Segurança
A cópia da Julinha foi preparada sem tokens, bancos de dados, IDs pessoais ou perfis de feeds predefinidos. A configuração de feeds foi transferida vazia; preencha-a apenas localmente. O bot principal da raiz foi mantido sem alterações nesta migração.

## Versões
A versão anterior da Julinha está arquivada em `Julinha/Versions/1.7.1/`. A versão original também permanece no repositório [Julia-Chan](https://github.com/tsur0-0/Julia-Chan), incluindo o histórico de versões.
