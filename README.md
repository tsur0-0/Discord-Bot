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

## Iniciar no Linux

Na pasta deste README, instale as dependências no ambiente virtual que você já usa:

```bash
musica-env/bin/python -m pip install -r requirements.txt
musica-env/bin/python bot.py
```

Se o ambiente virtual estiver em outro local, substitua `musica-env/bin/python` pelo caminho correto do Python dele.

O arquivo `private/TOKEN.env` deve conter `DISCORD_TOKEN=SEU_TOKEN`. O token não deve ser enviado a outras pessoas nem publicado em repositórios.

## Testar sem iniciar o Discord

```bash
musica-env/bin/python -m unittest discover -s tests -v
```

Os testes configuram caminhos temporários para não sobrescrever os dados reais.

## Atualizações e versões

- Edite o código ativo em `bot.py`.
- Edite os valores de configuração em `config.py`.
- Não execute arquivos de `versions/`: eles são cópias históricas.
- Faça backup da pasta `data/` antes de atualizar.
