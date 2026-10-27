PAGES = [
    ("home", "Início", "\U0001f3e0"),
    ("profile", "Perfil", "\U0001f9d1"),
    ("mod", "Moderação", "\u2694\ufe0f"),
    ("roles", "Cargos e Níveis", "\U0001f6e1\ufe0f"),
    ("logs", "Logs e Estatísticas", "\U0001f4d6"),
    ("config", "Configurações", "\u2699\ufe0f"),
    ("fun", "Diversão", "\U0001f48e"),
]

LOG_CATEGORIES = {
    "mensagem": "Mensagens",
    "membro": "Membros",
    "punicao": "Punições",
    "cargo": "Cargos",
    "canal": "Canais e permissões",
    "config": "Configurações",
    "comando": "Comandos admin",
    "auditoria": "Outras ações (auditoria)",
}

# chave: (nome, descrição, título desbloqueado ou None)
ACHIEVEMENTS = {
    "primeira_msg": ("Primeiros Passos", "Envie sua primeira mensagem", "Novato"),
    "msgs_100": ("Tagarela", "Envie 100 mensagens", "Tagarela"),
    "msgs_1000": ("Voz do Servidor", "Envie 1000 mensagens", "Voz do Servidor"),
    "nivel_5": ("Minerador", "Alcance o nível 5", "Minerador"),
    "nivel_10": ("Explorador", "Alcance o nível 10", "Explorador"),
    "nivel_25": ("Lenda do Nether", "Alcance o nível 25", "Lenda do Nether"),
    "amigo": ("Parceiro de Aventura", "Alcance 50 de afinidade com alguém", "Parceiro"),
    "segredo": ("Herobrine Esteve Aqui", "Descubra um segredo", "Caçador de Segredos"),
}

ACCENTS = {
    "verde": (91, 135, 49),
    "azul": (70, 130, 220),
    "vermelho": (200, 70, 70),
    "dourado": (230, 180, 50),
    "roxo": (140, 90, 200),
    "diamante": (80, 220, 210),
}

DEFAULT_WELCOMES = [
    "\u26cf\ufe0f {user} spawnou em **{server}**! Já somos {count} aventureiros.",
    "Um {user} selvagem apareceu! Bem-vindo(a) a **{server}** \U0001f332",
    "Bem-vindo(a), {user}! Pegue uma picareta e fique à vontade em **{server}**.",
]

RANDOM_PHRASES = [
    "Alguém lembrou de alimentar os cachorros? \U0001f43a",
    "Psiu... ouvi um sssss atrás de mim.",
    "Hoje é um bom dia para minerar diamantes. \U0001f48e",
    "Dica do dia: nunca cave diretamente para baixo.",
    "Quem aí já dormiu hoje? A noite está cheia de zumbis. \U0001f9df",
]

MEMES = [
    "Eu: vou dormir cedo.\nTambém eu às 3h da manhã: *só mais um bloco*.",
    "Programador: funciona na minha máquina.\nCreeper: sssssss...",
    "Nível de confiança ao cavar: 100%.\nNível de lava embaixo: 100%.",
    "'Só vou testar rapidinho' — última frase antes de 4 horas de debug.",
    "Bug resolvido!\n...criou outros três.",
]

JOKES = [
    "Por que o Creeper foi mal na prova? Porque explodiu na hora H. \U0001f4a5",
    "O que o Enderman disse ao pegar o bloco? 'Desculpa, é que eu amo essa vista.'",
    "Qual o animal favorito do minerador? O tatu... porque cava fundo.",
]

EIGHTBALL = [
    "Sim, com certeza.", "Provavelmente sim.", "Os sinais apontam que sim.",
    "Pergunte de novo mais tarde.", "Não conte com isso.", "Minhas fontes dizem não.",
    "Nem o Notch sabe.",
]

# palavra gatilho -> resposta (easter eggs)
EASTER = {
    "creeper": "Sssssss... \U0001f4a5 (calma, não vou explodir. Hoje.)",
    "herobrine": "\U0001f441\ufe0f Ele sempre esteve aqui...",
    "notch": "Ele não pode te ouvir, mas eu sim. \U0001f3a9",
}

AFFINITY_STAGES = [
    (0, "Desconhecidos"), (20, "Conhecidos"), (50, "Amigos"),
    (100, "Melhores amigos"), (200, "Irmãos de aventura"),
]
