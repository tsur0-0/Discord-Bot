# Julinha Chan — versão 1.8

Bot de comunidade para Discord, separado do bot principal do repositório.

## Funções
- Perfis, XP, níveis, ranking e preferências (sem sistema de conquistas).
- Amizade/afinidade e comandos secretos.
- Boas-vindas somente quando canal **e mensagem** forem configurados.
- Moderação, logs, auditoria e configuração administrativa.
- Detecção de links do YouTube, TikTok e Instagram nos canais configurados.
- Monitoramento opcional de feeds sociais, sem perfis pré-configurados.
- Status manual/automático do bot.

## Instalação
Na pasta `Julinha/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Preencha `DISCORD_TOKEN` no `.env` e execute `bash executar.sh`.

## Configuração segura
- `server_settings.json.example` é um modelo vazio. Copie para `server_settings.json` e configure seus próprios canais/perfis.
- `.env`, `server_settings.json`, banco de dados e ambientes virtuais são arquivos locais e não devem ser enviados ao GitHub.
- O bot não envia DM de inicialização para um ID pessoal.
- O código não inclui token nem IDs pessoais pré-configurados.

## Versão
- **1.8:** migração para o repositório Discord-Bot; remoção das conquistas e mensagens de conquista; boas-vindas sem mensagem automática padrão; remoção de IDs pessoais da configuração e de perfis de feeds predefinidos.
- A versão 1.7.1 continua disponível no repositório original Julia-Chan.
