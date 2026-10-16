# Discord Bot

## Estrutura

- `bot.py` — código ativo do bot. É este arquivo que você executa.
- `config.py` — versão, regras da economia, IDs e caminhos.
- `private/TOKEN.env` — token do Discord. Não compartilhe este arquivo.
- `data/data.json` — progresso dos jogadores.
- `data/meta.json` — dados auxiliares do mercado e códigos promocionais.
- `data/bot_profile.json` — bio e status personalizados do bot.
- `versions/` — versões antigas preservadas; não são usadas ao iniciar o bot.
- `tests/` — testes automatizados.
- `requirements.txt` — bibliotecas Python necessárias.

- `Alguns desses arquivos são criados após o início do bot`

## Atualizações e versões

- Edite o código ativo em `bot.py`.
- Edite os valores de configuração em `config.py`.
- Não execute arquivos de `versions/`: eles são cópias históricas.
- Faça backup da pasta `data/` antes de atualizar.
