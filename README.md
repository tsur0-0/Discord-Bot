# Discord Bot — Julinha Chan 1.8

## Aviso importante

**Este projeto é uma versão para estudos e aprendizado, não uma versão garantida para produção.** Partes do código foram criadas ou tiveram auxílio de ferramentas de inteligência artificial (IA). O código pode conter erros, inconsistências ou soluções que precisam ser revisadas. Leia, entenda, teste e adapte antes de usar em um servidor real.

## O que é

Bot de comunidade para Discord com perfis, XP e níveis, amizade/afinidade, moderação, logs, configurações administrativas, painéis e detecção opcional de links e feeds sociais.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Coloque o token de uma **aplicação de bot oficial do Discord** na variável `DISCORD_TOKEN` do `.env`. Depois, configure `server_settings.json` a partir de `server_settings.json.example` e execute:

```bash
bash executar.sh
```

## Segurança e dados

- Não envie `.env`, tokens, bancos de dados, arquivos locais de configuração ou dados de usuários para o GitHub.
- `server_settings.json.example` é um modelo vazio; canais e perfis monitorados devem ser configurados localmente.
- A versão ativa não contém sistema de conquistas nem mensagens de conquista.
- Boas-vindas só são enviadas quando o canal e a mensagem são configurados.

## Versões arquivadas

- `Versions/1.7.1/` — versão anterior da Julinha, preservada para consulta.
- `Versions/1.3.2/` — cópia histórica do bot que anteriormente ocupava a raiz deste repositório; IDs pessoais foram sanitizados e arquivos secretos não foram incluídos.

**Não execute os arquivos dentro de `Versions/`: são cópias históricas, não a versão ativa.**
