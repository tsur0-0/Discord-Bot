"""
Configurações centrais do bot: versão, administradores, caminhos, tempos de espera,
valores da economia, tabelas de jogo e perfil/presença.

Para ajustar o jogo, mexa AQUI em vez de procurar a variável no bot.py.
Segredos (token, chaves de API) vêm SEMPRE de variáveis de ambiente / .env,
nunca ficam escritos no código.
"""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv

    # Carrega o token do arquivo privado do projeto, sem depender do diretório atual.
    load_dotenv(ROOT_DIR / "private" / "TOKEN.env")
    load_dotenv(ROOT_DIR / ".env", override=False)
except ImportError:
    pass

# ----------------------------------------------------------------------------
# Versão
# ----------------------------------------------------------------------------
BOT_VERSION = "1.3.2"

# ----------------------------------------------------------------------------
# Segredos (apenas do ambiente)
# ----------------------------------------------------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GIANTBOMB_KEY = os.getenv("GIANTBOMB_KEY")  # opcional (grátis em giantbomb.com/api)

# ----------------------------------------------------------------------------
# Caminhos dos arquivos
# ----------------------------------------------------------------------------
def _caminho_arquivo(variavel: str, padrao: Path) -> Path:
    """Usa o caminho configurado no ambiente ou um caminho padrão dentro do projeto."""
    valor = os.getenv(variavel)
    return Path(valor).expanduser() if valor else padrao


PROFILE_FILE = _caminho_arquivo("BOT_PROFILE_FILE", ROOT_DIR / "data" / "bot_profile.json")
DATA_FILE = _caminho_arquivo("DATA_FILE", ROOT_DIR / "data" / "data.json")
META_FILE = DATA_FILE.with_name("meta.json")  # mercado e códigos promocionais

# ----------------------------------------------------------------------------
# Administradores
# ----------------------------------------------------------------------------


def _ids_do_ambiente(nome: str, padrao: set[int]) -> set[int]:
    """Lê uma lista de IDs separados por vírgula (ex.: BOT_ADMIN_IDS=1,2); usa o padrão se não houver."""
    bruto = os.getenv(nome, "")
    ids = {int(p) for p in bruto.replace(" ", "").split(",") if p.isdigit()}
    return ids or set(padrao)


ADMIN_IDS = _ids_do_ambiente("BOT_ADMIN_IDS", {0, 0})  # /status, /codigos criar...
CHANGE_USER_ID = int(os.getenv("BOT_CHANGE_USER_ID", "0"))  # quem usa $change e $help

# ----------------------------------------------------------------------------
# Perfil e presença do bot (valores iniciais; o /status e /bio gravam em PROFILE_FILE)
# ----------------------------------------------------------------------------
PERFIL_PADRAO = {"status": "Vendo Overlow", "bio": ""}

# ----------------------------------------------------------------------------
# Economia
# ----------------------------------------------------------------------------
BASE_LUCRO = 1.0  # 1 real por segundo
BASE_AMOR = 0.10  # pontos de relacionamento por segundo (total, dividido entre as Mains)
CUSTO_CRESCIMENTO = 1.22  # cada unidade comprada deixa a próxima 22% mais cara (era 15%)
MAX_SLOTS = 5
RENASCER_MIN = 5_000  # lucro/s bruto mínimo para poder renascer
BONUS_RENASCER = 10  # % permanente de dinheiro e amor por renascimento
PRESENTE_EXPOENTE = 0.75  # pontos de amor = valor ** expoente / 10

# ----------------------------------------------------------------------------
# Níveis
# ----------------------------------------------------------------------------
CARGO_NOME = "Deus do amor"  # cargo dado quando uma Main chega no nível máximo
PONTOS_NIVEL_2 = 15  # pontos para sair do nível 1 (era 10)
MULT_NIVEL = 3.3  # cada nível exige 3,3x o anterior (era 3x)

# ----------------------------------------------------------------------------
# Tempos de espera (segundos)
# ----------------------------------------------------------------------------
TRABALHO_ESPERA = 5 * 60  # /trabalhar
ENCONTRO_ESPERA = 2 * 3600  # /encontro
DUELO_ESPERA = 10 * 60
DIARIO_ESPERA = 20 * 3600  # 20h entre resgates
DIARIO_LIMITE = 48 * 3600  # passou disso, a sequência zera
TEMPO_SESSAO = 300.0  # intervalo máximo entre comandos para contar como a mesma sessão
TEMPO_INICIO = 30.0  # crédito fixo ao abrir uma sessão nova

# ----------------------------------------------------------------------------
# Eventos aleatórios
# ----------------------------------------------------------------------------
EVENTO_CHANCE = 0.15
EVENTO_COOLDOWN = 45  # segundos entre eventos do mesmo player

# ----------------------------------------------------------------------------
# Casamento e duelo
# ----------------------------------------------------------------------------
CASAMENTO_NIVEL = 20
CASAMENTO_CLASSE = 2  # Ouro
CASAMENTO_ENCONTROS = 10
CASAMENTO_BONUS = 5  # % permanente de dinheiro e amor
CASAMENTO_FRAGMENTOS = 25
DUELO_FRAGMENTOS = 1

# ----------------------------------------------------------------------------
# Coleção, histórico e mercado
# ----------------------------------------------------------------------------
LOG_MAX = 60
ALBUM_META = 200  # personagens para o álbum ficar 100% completo
POR_PAGINA = 10
MERCADO_TAXA = 0.05
MERCADO_MAX_ANUNCIOS = 5

# ----------------------------------------------------------------------------
# Visual e comandos ocultos
# ----------------------------------------------------------------------------
ROSA = 0xFF69B4
PREFIXO = "$"
MAX_FLOAT = 1e30
MAX_INT = 10**12
MAX_ITEM = 3000  # 1,22**3000 ainda cabe num float; acima disso o custo estoura

# ----------------------------------------------------------------------------
# Tabelas do jogo
# ----------------------------------------------------------------------------
# tipo "lucro": soma em reais/s | tipo "amor": soma em pontos de relacionamento/s
ITEMS = {
    "bico": dict(nome="Entregador de Ifood", emoji="🏍️", tipo="lucro", valor=1, base=50),
    "freela": dict(nome="Freelancer", emoji="💻", tipo="lucro", valor=5, base=300),
    "loja": dict(nome="Lojinha", emoji="🏪", tipo="lucro", valor=25, base=2_000),
    "startup": dict(nome="Startup", emoji="🚀", tipo="lucro", valor=150, base=15_000),
    "imperio": dict(nome="Império", emoji="🏰", tipo="lucro", valor=1_000, base=120_000),
    "conglomerado": dict(nome="Conglomerado", emoji="🏢", tipo="lucro", valor=10_000, base=1_500_000),
    "multinacional": dict(nome="Multinacional", emoji="🌐", tipo="lucro", valor=100_000, base=20_000_000),
    "banco": dict(nome="Banco próprio", emoji="🏦", tipo="lucro", valor=1_000_000, base=300_000_000),
    "monopolio": dict(nome="Monopólio mundial", emoji="🌍", tipo="lucro", valor=10_000_000, base=5_000_000_000),
    "espacial": dict(nome="Empresa espacial", emoji="🛰️", tipo="lucro", valor=100_000_000, base=100_000_000_000),
    "galaxia": dict(nome="Império galáctico", emoji="🌌", tipo="lucro", valor=1_000_000_000, base=2_000_000_000_000),
    "cartinha": dict(nome="Cartinha de amor", emoji="💌", tipo="amor", valor=0.02, base=40),
    "flores": dict(nome="Buquê de flores", emoji="💐", tipo="amor", valor=0.05, base=100),
    "jantar": dict(nome="Jantar romântico", emoji="🍷", tipo="amor", valor=0.10, base=600),
    "presente": dict(nome="Presentes caros", emoji="🎁", tipo="amor", valor=0.25, base=4_000),
    "viagem": dict(nome="Viagem a dois", emoji="✈️", tipo="amor", valor=0.50, base=30_000),
    "casa": dict(nome="Casa juntos", emoji="🏡", tipo="amor", valor=1.00, base=250_000),
    "alianca": dict(nome="Aliança de ouro", emoji="💍", tipo="amor", valor=10, base=1_000_000),
    "cerimonia": dict(nome="Cerimônia de casamento", emoji="💒", tipo="amor", valor=100, base=15_000_000),
    "lua": dict(nome="Lua de mel", emoji="🌙", tipo="amor", valor=1_000, base=250_000_000),
    "mansao": dict(nome="Mansão dos sonhos", emoji="🏯", tipo="amor", valor=10_000, base=4_000_000_000),
    "ilha": dict(nome="Ilha particular", emoji="🏝️", tipo="amor", valor=100_000, base=60_000_000_000),
    "templo": dict(nome="Templo do amor", emoji="⛩️", tipo="amor", valor=1_000_000, base=1_000_000_000_000),
    "estrelas": dict(nome="Constelação com o nome de vocês", emoji="✨", tipo="amor", valor=10_000_000, base=20_000_000_000_000),
    "eternidade": dict(nome="Eternidade juntos", emoji="♾️", tipo="amor", valor=100_000_000, base=400_000_000_000_000),
}

NOMES_NIVEIS = [
    "Arqui-inimigo", "Inimigo", "Rival", "Antipatia", "Indiferente",
    "Desconhecidos", "Conhecidos", "Colegas", "Amigos", "Bons amigos",
    "Melhores amigos", "Confidentes", "Admiração", "Paquera", "Crush",
    "Interesse mútuo", "Primeiro encontro", "Ficantes", "Namorando", "Namoro sério",
    "Apaixonados", "Noivos", "Casados", "Amor eterno", "Almas gêmeas",
]
NIVEL_MAX = len(NOMES_NIVEIS)  # 25

# (nome, emoji, pontos de classe mínimos, bônus % em dinheiro e amor)
CLASSES = [
    ("Bronze", "🥉", 0, 0),
    ("Prata", "🥈", 40, 3),
    ("Ouro", "🥇", 120, 6),
    ("Platina", "💠", 300, 10),
    ("Diamante", "💎", 700, 15),
    ("Mestre", "🔮", 1200, 20),
    ("Grão-Mestre", "👑", 2000, 26),
    ("Lenda", "🌟", 3200, 33),
    ("Mítico", "🐉", 5000, 41),
    ("Divino", "☄️", 8000, 50),
]

# (nome, emoji, cor, fragmentos que uma repetida rende)
RARIDADES = [
    ("comum", "⬜", 0x95A5A6, 1),
    ("rara", "🟦", 0x3498DB, 3),
    ("épica", "🟪", 0x9B59B6, 8),
    ("lendária", "🟧", 0xF39C12, 20),
    ("mítica", "🟥", 0xE74C3C, 50),
]

# id -> (emoji, nome, custo em fragmentos (None = não vendável), cor do cartão)
MOLDURAS = {
    "flor": ("🌸", "Flor de cerejeira", 10, 0xFFB7C5),
    "dourada": ("✨", "Moldura dourada", 30, 0xFFD700),
    "cristal": ("💎", "Cristal", 60, 0x00BFFF),
    "chamas": ("🔥", "Chamas eternas", 100, 0xFF4500),
    "cosmos": ("🌌", "Cosmos", 200, 0x6A5ACD),
    "alianca": ("💍", "Aliança (exclusiva do casamento)", None, 0xEEEEEE),
}

# Presentes: seg = quantos segundos de lucro o presente custa; amor = fração do nível atual
PRESENTES = {
    "rosa": dict(emoji="🌹", nome="Rosa", seg=300, amor=0.05),
    "chocolate": dict(emoji="🍫", nome="Caixa de chocolate", seg=800, amor=0.08, buff=("amor", 1.5, 180)),
    "ursinho": dict(emoji="🧸", nome="Ursinho de pelúcia", seg=2_500, amor=0.15),
    "perfume": dict(emoji="🧴", nome="Perfume importado", seg=5_000, amor=0.10, buff=("lucro", 1.5, 300)),
    "anel": dict(emoji="💍", nome="Anel de promessa", seg=40_000, amor=0.25, bonus=0.2, limite=10),
    "colar": dict(emoji="📿", nome="Colar de diamantes", seg=100_000, amor=0.40),
}

# Prestígio: id -> (emoji, nome, descrição por nível, nível máximo, custo base)
PRESTIGIO = {
    "lucro": ("💰", "Mente empresarial", "+5% de dinheiro", 10, 1),
    "amor": ("❤️", "Coração dourado", "+5% de amor", 10, 1),
    "desconto": ("🏷️", "Pechincha", "-2% no custo dos upgrades", 10, 2),
    "tempo": ("⏱️", "Agilidade", "-5% nas esperas de /trabalhar e /encontro", 6, 2),
    "sorteio": ("🎟️", "Sortudo", "-4% no custo do /sorteio", 5, 2),
    "slot": ("💞", "Coração expandido", "+1 slot de Main", 2, 6),
}
