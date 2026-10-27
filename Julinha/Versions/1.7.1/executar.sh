#!/usr/bin/env bash
# Instala as dependências na primeira execução e inicia a Julinha.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=".venv"
MARCA="$VENV/.dependencias_ok"

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 não encontrado. Instale o Python 3.10 ou superior." >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "❌ É necessário Python 3.10 ou superior (discord.py 2.4)." >&2
    exit 1
fi

if [ ! -d "$VENV" ]; then
    echo "📦 Criando ambiente virtual em $VENV ..."
    python3 -m venv "$VENV" || {
        echo "❌ Falha ao criar o venv. No Debian/Ubuntu: sudo apt install python3-venv" >&2
        exit 1
    }
fi

# Reinstala só se for a primeira vez ou se o requirements.txt mudou.
if [ ! -f "$MARCA" ] || [ requirements.txt -nt "$MARCA" ]; then
    echo "📦 Instalando dependências (discord.py, aiosqlite, Pillow) ..."
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r requirements.txt
    touch "$MARCA"
fi

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "📝 Criei o arquivo .env. Abra-o, coloque o token em DISCORD_TOKEN e rode ./executar.sh de novo."
    else
        echo "❌ Arquivo .env não encontrado. Crie-o com a linha DISCORD_TOKEN=seu_token." >&2
    fi
    exit 1
fi

echo "🚀 Iniciando a Julinha ..."
exec "$VENV/bin/python" bot.py
