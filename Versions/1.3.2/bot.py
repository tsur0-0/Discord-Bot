"""
Bot de Discord: busca de waifu + simulador de namoro (v2).

Comandos:
- /waifu nome   -> busca personagem de anime/mangá, visual novels e jogos
                   e escolhe como Main (se tiver slot livre)
- /perfil       -> dinheiro, lucro/s, classe, bônus e todas as suas Mains
- /classe       -> mostra Bronze -> Diamante e seu progresso
- /loja         -> lista upgrades
- /comprar      -> compra upgrades (lucro ou relacionamento)
- /diario       -> recompensa diária com sequência (streak)
- /remover      -> remove uma Main (perde o progresso de amor dela)
- /resetar      -> recomeça do zero
- /trabalhar    -> bico rápido (a cada 5 min) para ganhar dinheiro
- /encontro     -> leva uma Main para sair (paga dinheiro, ganha amor, a cada 2h)
- /presentear   -> gasta dinheiro para dar pontos de amor a uma Main
- /renascer     -> recomeça o dinheiro/upgrades em troca de bônus permanente (+10%)
- /conquistas   -> lista de conquistas, cada uma com recompensa
- /ranking      -> top 10 jogadores (classe, dinheiro, lucro, renascimentos e várias estatísticas)
- /casal        -> cartão personalizado de uma Main (nível, afinidade, imagem)
- /presentes    -> catálogo de presentes com efeitos diferentes
- /casamento    -> cerimônia desbloqueável com requisitos e recompensas
- /titulos      -> títulos equipáveis (conquistas, casamento, álbum...)
- /prestigio    -> árvore de habilidades de quem já renasceu
- /duelo        -> duelo entre jogadores, com aposta opcional
- /sorteio      -> sorteio de personagem ou recompensa com dinheiro do jogo
- /historico    -> últimos eventos, compras e mudanças de nível
- /colecao      -> todas as personagens obtidas (separada das Mains), raridades e álbum
- /equipar      -> coloca uma personagem da coleção num slot (mantém o progresso)
- /molduras     -> gasta fragmentos em molduras
- /mercado      -> compra e venda de fragmentos, molduras e personagens (ver/vender/comprar/cancelar)
- /help         -> lista todos os comandos
- /codigos      -> códigos promocionais (resgatar; criar/listar/apagar para admins)

Regras:
- Lucro base: 1 real/s + upgrades. Amor base: 0,10 pt/s + upgrades.
- O amor gerado é DIVIDIDO entre todas as suas Mains.
- Cada Main tem seu próprio nível (1..25). Subir de nível dá:
    * Pontos de Classe (valem o número do nível que você alcançou)
    * Recompensa: nível múltiplo de 5 = +1 slot de Main (máx. 5);
      nível ímpar = +1% dinheiro; nível par = +1% amor
  (cada personagem só rende recompensa/pontos uma vez por nível)
- Classes (Bronze, Prata, Ouro, Platina, Diamante) dão bônus % de dinheiro e amor.
- Ao enviar qualquer comando pode rolar um evento aleatório, bom ou ruim.
"""
import asyncio
import hashlib
import json
import math
import os
import random
import re
import time
import unicodedata
from pathlib import Path
from typing import NamedTuple
import wavelink
import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks

from config import (
    BOT_VERSION,
    TOKEN,
    GIANTBOMB_KEY,
    PROFILE_FILE,
    DATA_FILE,
    META_FILE,
    ADMIN_IDS,
    CHANGE_USER_ID,
    PERFIL_PADRAO,
    BASE_LUCRO,
    BASE_AMOR,
    CUSTO_CRESCIMENTO,
    MAX_SLOTS,
    RENASCER_MIN,
    BONUS_RENASCER,
    PRESENTE_EXPOENTE,
    CARGO_NOME,
    PONTOS_NIVEL_2,
    MULT_NIVEL,
    TRABALHO_ESPERA,
    ENCONTRO_ESPERA,
    DUELO_ESPERA,
    DIARIO_ESPERA,
    DIARIO_LIMITE,
    TEMPO_SESSAO,
    TEMPO_INICIO,
    EVENTO_CHANCE,
    EVENTO_COOLDOWN,
    CASAMENTO_NIVEL,
    CASAMENTO_CLASSE,
    CASAMENTO_ENCONTROS,
    CASAMENTO_BONUS,
    CASAMENTO_FRAGMENTOS,
    DUELO_FRAGMENTOS,
    LOG_MAX,
    ALBUM_META,
    POR_PAGINA,
    MERCADO_TAXA,
    MERCADO_MAX_ANUNCIOS,
    ROSA,
    PREFIXO,
    MAX_FLOAT,
    MAX_INT,
    MAX_ITEM,
    ITEMS,
    NOMES_NIVEIS,
    NIVEL_MAX,
    CLASSES,
    RARIDADES,
    MOLDURAS,
    PRESENTES,
    PRESTIGIO,
)


def carregar_perfil_bot():
    padrao = dict(PERFIL_PADRAO)
    try:
        if PROFILE_FILE.exists():
            dados = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                padrao.update({k: v for k, v in dados.items() if k in padrao and isinstance(v, str)})
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[perfil] Não foi possível ler {PROFILE_FILE}: {exc}")
    return padrao

def salvar_perfil_bot():
    temporario = PROFILE_FILE.with_suffix(PROFILE_FILE.suffix + ".tmp")
    temporario.write_text(json.dumps(PERFIL_BOT, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(PROFILE_FILE)

PERFIL_BOT = carregar_perfil_bot()


# ----------------------------------------------------------------------------
# Regras do jogo
# ----------------------------------------------------------------------------






def limiar(n: int) -> int:
    """Pontos mínimos para estar no nível n (1..25)."""
    return 0 if n <= 1 else int(PONTOS_NIVEL_2 * MULT_NIVEL ** (n - 2))


def _br(s: str) -> str:
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt(n: float, casas: int | None = None) -> str:
    """Formata no padrão brasileiro (1.234,56); números enormes viram 1,5 bi etc."""
    if abs(n) >= 1_000_000:
        for div, nome in (
            (1e21, "sext"), (1e18, "quint"), (1e15, "quad"),
            (1e12, "tri"), (1e9, "bi"), (1e6, "mi"),
        ):
            if abs(n) >= div:
                return _br(f"{n / div:,.2f}").rstrip("0").rstrip(",") + f" {nome}"
    if casas is None:
        casas = 0 if abs(n - round(n)) < 0.005 else 2
    return _br(f"{n:,.{casas}f}")


def custo(chave: str, possui: int, u: dict | None = None) -> int:
    c = ITEMS[chave]["base"] * CUSTO_CRESCIMENTO**possui
    if u is not None:
        c *= max(0.2, 1 - 0.02 * u.get("prest", {}).get("desconto", 0))
    return int(c)


def classe_de(cp: float) -> tuple[int, str, str, int, int | None]:
    """(índice, nome, emoji, bônus %, pontos do próximo rank ou None)."""
    idx = 0
    for i, (_, _, minimo, _) in enumerate(CLASSES):
        if cp >= minimo:
            idx = i
    nome, emoji, _, bonus = CLASSES[idx]
    prox = CLASSES[idx + 1][2] if idx + 1 < len(CLASSES) else None
    return idx, nome, emoji, bonus, prox


def lucro_por_segundo(u: dict) -> float:
    """Lucro bruto (só base + upgrades, sem bônus %)."""
    total = BASE_LUCRO
    for k, qtd in u["items"].items():
        if ITEMS[k]["tipo"] == "lucro":
            total += ITEMS[k]["valor"] * qtd
    return round(total, 2)


def penalidade(rps: float) -> float:
    """Quanto mais lucro/s, menos amor. 1000/s => 0,06. Cresce devagar (log)."""
    return round(0.06 * math.log10(max(rps, 1)) / 3, 2)


def amor_bruto(u: dict) -> float:
    total = BASE_AMOR
    for k, qtd in u["items"].items():
        if ITEMS[k]["tipo"] == "amor":
            total += ITEMS[k]["valor"] * qtd
    return round(total, 2)


def amor_por_segundo(u: dict) -> float:
    """Amor total/s (sem bônus %), que será dividido entre as Mains."""
    return max(0.0, round(amor_bruto(u) - penalidade(lucro_por_segundo(u)), 2))


def mult(tipo: str, u: dict, t0: float, t1: float) -> float:
    """Multiplicador de 'lucro' ou 'amor' no intervalo [t0, t1]: bônus permanentes + classe + buffs."""
    bonus = (
        u.get(f"b_{tipo}", 0)
        + classe_de(u["cp"])[3]
        + u.get("renasc", 0) * BONUS_RENASCER
        + u.get("prest", {}).get(tipo, 0) * 5
    )
    base = 1 + bonus / 100
    dt = t1 - t0
    extra = 0.0
    for b in u["buffs"]:
        if b["t"] != tipo:
            continue
        if dt <= 0:
            if b["ate"] > t1:
                extra += b["m"] - 1
        else:
            sobreposicao = max(0.0, min(t1, b["ate"]) - t0)
            extra += (sobreposicao / dt) * (b["m"] - 1)
    return max(0.0, base * (1 + extra))


def lucro_efetivo(u: dict) -> float:
    agora = time.time()
    return lucro_por_segundo(u) * mult("lucro", u, agora, agora)


def amor_efetivo(u: dict) -> float:
    """Amor/s total já com bônus (antes de dividir entre as Mains)."""
    agora = time.time()
    return amor_por_segundo(u) * mult("amor", u, agora, agora)


def nivel(pontos: float) -> tuple[int, str, float | None]:
    """Retorna (nível 1..25, nome, pontos mínimos do próximo nível ou None)."""
    n = 1
    for i in range(1, NIVEL_MAX + 1):
        if pontos >= limiar(i):
            n = i
    prox = limiar(n + 1) if n < NIVEL_MAX else None
    return n, NOMES_NIVEIS[n - 1], prox


def aplicar_premio(u: dict, lv: int) -> str:
    """Recompensa por alcançar o nível lv (primeira vez para aquela personagem)."""
    if lv % 5 == 0 and u["slots"] < MAX_SLOTS:
        u["slots"] += 1
        return f"🎟️ +1 slot de Main ({u['slots']}/{MAX_SLOTS})"
    if lv % 2 == 1:
        u["b_lucro"] += 1
        return f"💰 +1% de dinheiro (total {u['b_lucro']}%)"
    u["b_amor"] += 1
    return f"❤️ +1% de amor (total {u['b_amor']}%)"


# (id, emoji, nome, descrição, condição, recompensa)  recompensa = (tipo, valor)
#   "dinheiro": valor = segundos de lucro | "lucro"/"amor": +valor % permanente
CONQUISTAS = [
    ("dupla", "👭", "Dupla dinâmica", "Ter 2 slots de Main", lambda u: u["slots"] >= 2, ("amor", 1)),
    ("harem", "💞", "Coração grande", "Ter 3 slots de Main", lambda u: u["slots"] >= 3, ("lucro", 1)),
    ("amor10", "💘", "Quase lá", "Levar uma Main ao nível 10", lambda u: max(u["hist"].values(), default=1) >= 10, ("dinheiro", 600)),
    ("amor20", "💍", "Pra vida toda", "Levar uma Main ao nível 20", lambda u: max(u["hist"].values(), default=1) >= 20, ("amor", 2)),
    ("ouro", "🥇", "Ouro puro", "Chegar à classe Ouro", lambda u: classe_de(u["cp"])[0] >= 2, ("lucro", 2)),
    ("diamante", "💎", "Brilhante", "Chegar à classe Diamante", lambda u: classe_de(u["cp"])[0] >= 4, ("amor", 2)),
    ("lenda", "🌟", "Lendário", "Chegar à classe Lenda", lambda u: classe_de(u["cp"])[0] >= 7, ("lucro", 3)),
    ("serie7", "🔥", "Fiel", "Sequência de 7 dias no /diario", lambda u: u["streak"] >= 7, ("dinheiro", 1800)),
    ("serie30", "📅", "Devoção", "Sequência de 30 dias no /diario", lambda u: u["streak"] >= 30, ("amor", 3)),
    ("colecionador", "🛍️", "Consumista", "Ter 50 upgrades comprados", lambda u: sum(u["items"].values()) >= 50, ("dinheiro", 900)),
    ("magnata", "🏦", "Magnata", "Chegar a R$ 100 mil/s de lucro bruto", lambda u: lucro_por_segundo(u) >= 100_000, ("lucro", 2)),
    ("renascido", "🔁", "Renascido", "Fazer o primeiro /renascer", lambda u: u.get("renasc", 0) >= 1, ("amor", 2)),
    ("deus", "⛩️", "Deus do amor", "Levar uma Main ao nível máximo", lambda u: bool(u.get("deus")), ("lucro", 5)),
    ("casamento", "💒", "Até que a morte...", "Realizar o /casamento", lambda u: bool(u.get("casada")), ("lucro", 3)),
    ("album25", "📚", "Colecionador", "Ter 50 personagens na coleção", lambda u: len(u["colecao"]) >= 50, ("amor", 2)),
    ("duelo5", "⚔️", "Gladiador", "Vencer 5 duelos", lambda u: u["vitorias"] >= 5, ("dinheiro", 1800)),
    ("prest5", "🌳", "Sábio", "Gastar 5 pontos de prestígio", lambda u: u["prest_gasto"] >= 5, ("amor", 2)),
]


def _premio_conq(u: dict, tipo: str, v: float) -> str:
    if tipo == "dinheiro":
        g = max(500.0, lucro_efetivo(u) * v)
        add_money(u, g)
        return f"💰 +R$ {fmt(g)}"
    if tipo == "lucro":
        u["b_lucro"] += v
        return f"💰 +{v}% de dinheiro"
    u["b_amor"] += v
    return f"❤️ +{v}% de amor"


def checar_conquistas(u: dict) -> None:
    for cid, emoji, nome, _, ok, (tipo, v) in CONQUISTAS:
        if cid not in u["conq"] and ok(u):
            u["conq"].append(cid)
            avisar(u, f"🏅 Conquista: {emoji} **{nome}**! {_premio_conq(u, tipo, v)}")


def processar_niveis(u: dict) -> None:
    """Vê subidas de nível das Mains, dá pontos de classe/recompensas e guarda avisos."""
    classe_antes = classe_de(u["cp"])[0]
    for m in u["waifus"]:
        n, nome, _ = nivel(m["love"])
        ant = u["hist"].get(m["name"], 1)
        if n <= ant:
            continue
        premios = []
        for lv in range(ant + 1, n + 1):
            u["cp"] += lv
            premios.append(aplicar_premio(u, lv))
        u["hist"][m["name"]] = n
        avisar(u, 
            f"⬆️ **{m['name']}** chegou ao nível {n}/{NIVEL_MAX} (**{nome}**)! "
            f"+{sum(range(ant + 1, n + 1))} pts de classe\n" + "\n".join(premios)
        )
    nova = classe_de(u["cp"])
    if nova[0] > classe_antes:
        avisar(u, f"🏆 Sua classe subiu para **{nova[2]} {nova[1]}**! (+{nova[3]}% dinheiro e amor)")
    checar_conquistas(u)


def acumular(u: dict) -> None:
    """Credita o que foi ganho desde a última atualização."""
    agora = time.time()
    t0 = u["last"]
    dt = max(0.0, agora - t0)
    u["last"] = agora
    if dt > 0:
        add_money(u, lucro_por_segundo(u) * mult("lucro", u, t0, agora) * dt)
        if u["waifus"]:
            por_main = amor_por_segundo(u) * mult("amor", u, t0, agora) / len(u["waifus"])
            for m in u["waifus"]:
                m["love"] += por_main * dt
    u["buffs"] = [b for b in u["buffs"] if b["ate"] > agora]
    processar_niveis(u)


# ----------------------------------------------------------------------------
# Eventos aleatórios (rolam ao usar qualquer comando)
# ----------------------------------------------------------------------------


def _buff(u: dict, tipo: str, m: float, seg: int) -> None:
    u["buffs"].append({"t": tipo, "m": m, "ate": time.time() + seg})


# Cada evento é uma configuração; `rodar_evento` sabe executar cada "tipo".
#   ganho    -> dinheiro = max(minimo, lucro/s * mult)            (mult: número ou (min, max) inteiro)
#   perda    -> perde `pct` (min, max) do dinheiro atual
#   imposto  -> perde lucro/s * mult (no máximo o dinheiro que tem)
#   buff     -> multiplicador `mult` de lucro ou amor por `seg` segundos
#   amor     -> uma Main ganha/perde `pct` (min, max) do que falta/sobra no nível; `fallback` se já está no máximo
EVENTOS = [
    # bons
    dict(id="dinheiro", tipo="ganho", minimo=50.0, mult=(60, 300),
         msg="💸 **Evento:** você achou **R$ {v}** na rua!"),
    dict(id="presente", tipo="amor", sinal=+1, pct=(0.05, 0.12), fallback="dinheiro",
         msg="🎁 **Evento:** **{nome}** te deu um presente surpresa! +{v} pts de amor"),
    dict(id="promocao", tipo="buff", buff="lucro", mult=2.0, seg=300,
         msg="📈 **Evento:** promoção no trabalho! **Lucro x2** por 5 minutos"),
    dict(id="encontro", tipo="buff", buff="amor", mult=2.0, seg=300,
         msg="💘 **Evento:** encontro perfeito! **Amor x2** por 5 minutos"),
    dict(id="loteria", tipo="ganho", minimo=500.0, mult=1800,
         msg="🎰 **Evento:** você ganhou na loteria! **+R$ {v}**"),
    dict(id="heranca", tipo="ganho", minimo=1000.0, mult=3000,
         msg="📜 **Evento:** herança de um parente distante! **+R$ {v}**"),
    dict(id="declaracao", tipo="amor", sinal=+1, pct=(0.12, 0.25), fallback="heranca",
         msg="💌 **Evento:** **{nome}** fez uma declaração de amor! +{v} pts de amor"),
    dict(id="bolsa", tipo="buff", buff="lucro", mult=3.0, seg=120,
         msg="🚀 **Evento:** suas ações dispararam! **Lucro x3** por 2 minutos"),
    # ruins
    dict(id="assalto", tipo="perda", pct=(0.05, 0.15),
         msg="🥷 **Evento ruim:** você foi assaltado e perdeu **R$ {v}**"),
    dict(id="briga", tipo="amor", sinal=-1, pct=(0.03, 0.10),  # nunca faz perder nível
         msg="😤 **Evento ruim:** briga com **{nome}**! -{v} pts de amor"),
    dict(id="crise", tipo="buff", buff="lucro", mult=0.5, seg=300,
         msg="📉 **Evento ruim:** crise econômica! **Lucro x0,5** por 5 minutos"),
    dict(id="ciumes", tipo="buff", buff="amor", mult=0.5, seg=300,
         msg="💔 **Evento ruim:** ciúmes! **Amor x0,5** por 5 minutos"),
    dict(id="imposto", tipo="imposto", mult=120,
         msg="🧾 **Evento ruim:** cobrança de imposto! -**R$ {v}**"),
    dict(id="pneu", tipo="imposto", mult=90,
         msg="🛞 **Evento ruim:** pneu furado e conserto caro! -**R$ {v}**"),
]
EVENTOS_POR_ID = {ev["id"]: ev for ev in EVENTOS}


def rodar_evento(ev: dict, u: dict) -> str:
    """Aplica um evento da lista EVENTOS ao jogador e devolve a mensagem."""
    tipo = ev["tipo"]
    if tipo == "ganho":
        mult = ev["mult"]
        if isinstance(mult, tuple):
            mult = random.randint(*mult)
        g = max(ev["minimo"], lucro_efetivo(u) * mult)
        add_money(u, g)
        return ev["msg"].format(v=fmt(g))
    if tipo == "perda":
        p = round(u["money"] * random.uniform(*ev["pct"]), 2)
        u["money"] = round(u["money"] - p, 2)
        return ev["msg"].format(v=fmt(p))
    if tipo == "imposto":
        p = min(u["money"], round(lucro_efetivo(u) * ev["mult"], 2))
        u["money"] = round(u["money"] - p, 2)
        return ev["msg"].format(v=fmt(p))
    if tipo == "buff":
        _buff(u, ev["buff"], ev["mult"], ev["seg"])
        return ev["msg"]
    if tipo == "amor":
        m = random.choice(u["waifus"])
        n, _, prox = nivel(m["love"])
        if ev["sinal"] > 0:
            if prox is None:  # já no nível máximo: cai no evento reserva
                return rodar_evento(EVENTOS_POR_ID[ev["fallback"]], u)
            g = (prox - limiar(n)) * random.uniform(*ev["pct"])
            m["love"] += g
        else:
            g = (m["love"] - limiar(n)) * random.uniform(*ev["pct"])
            m["love"] -= g
        return ev["msg"].format(nome=m["name"], v=fmt(g))
    raise ValueError(f"tipo de evento desconhecido: {tipo}")


def coletar(u: dict) -> str | None:
    """Junta os avisos pendentes (níveis etc.) e talvez rola um evento aleatório."""
    msgs = list(u["pend"])
    u["pend"].clear()
    agora = time.time()
    if (
        u["waifus"]
        and agora - u.get("ult_evento", 0) >= EVENTO_COOLDOWN
        and random.random() < EVENTO_CHANCE
    ):
        u["ult_evento"] = agora
        ev = rodar_evento(random.choice(EVENTOS), u)
        logar(u, ev)
        msgs.append(ev)
        processar_niveis(u)  # um presente pode ter feito subir de nível
        msgs.extend(u["pend"])
        u["pend"].clear()
    return "\n".join(msgs) if msgs else None


# ----------------------------------------------------------------------------
# Persistência
# ----------------------------------------------------------------------------
def novo_user() -> dict:
    return {
        "money": 0.0,
        "waifus": [],  # Mains: {"name","image","anime","love"}
        "slots": 1,
        "items": {},
        "last": time.time(),
        "cp": 0,  # pontos de classe
        "hist": {},  # nome da personagem -> maior nível já recompensado
        "b_lucro": 0,  # % permanente de dinheiro
        "b_amor": 0,  # % permanente de amor
        "buffs": [],
        "pend": [],
        "deus": False,
        "diario": 0,
        "streak": 0,
        "ult_evento": 0,
        "renasc": 0,  # renascimentos (prestígio)
        "conq": [],  # ids das conquistas já recebidas
        "t_trab": 0,  # último /trabalhar
        "t_enc": 0,  # último /encontro
        # estatísticas
        "criado": time.time(),
        "ult_cmd": 0,
        "t_jogo": 0.0,  # segundos de jogo ativo
        "tot_money": 0.0,  # dinheiro acumulado na vida da conta
        "max_streak": 0,
        "n_enc": 0,
        "n_pres": 0,
        "hist_renasc": [],
        "log": [],  # histórico {"t","m"}
        # coleção
        "colecao": {},  # nome -> {"image","anime","tipo","qtd","love"}
        "fragmentos": 0,
        "molduras": [],
        "moldura": None,
        "titulo": None,
        # prestígio, casamento, duelos, presentes
        "prest": {},
        "prest_gasto": 0,
        "casada": None,
        "vitorias": 0,
        "derrotas": 0,
        "t_duelo": 0,
        "presentes_c": {},
    }


def migrar(u: dict) -> None:
    """Converte saves da versão antiga (uma waifu só) e garante todos os campos."""
    if "waifus" not in u:
        antigo = u.pop("waifu", None)
        love = u.pop("love", 0.0)
        u["waifus"] = [{**antigo, "love": love}] if antigo else []
        u.pop("nivel_visto", None)  # os níveis serão recalculados (e recompensados) normalmente
    for k, v in novo_user().items():
        u.setdefault(k, v)
    for m in u["waifus"]:  # toda Main também está na coleção
        u["colecao"].setdefault(
            m["name"], {"image": m["image"], "anime": m.get("anime"), "tipo": "anime", "qtd": 1, "love": 0.0}
        )


# ----------------------------------------------------------------------------
# Helpers: estatísticas, histórico, coleção, títulos, prestígio
# ----------------------------------------------------------------------------






def add_money(u: dict, g: float) -> None:
    """Soma dinheiro e conta no total acumulado da conta."""
    u["money"] = round(u["money"] + g, 2)
    if g > 0:
        u["tot_money"] = round(u["tot_money"] + g, 2)


def logar(u: dict, msg: str) -> None:
    u["log"].append({"t": int(time.time()), "m": msg})
    del u["log"][:-LOG_MAX]


def avisar(u: dict, msg: str) -> None:
    """Aviso que aparece no próximo comando e também vai pro /historico."""
    u["pend"].append(msg)
    logar(u, msg)


def pl(u: dict, chave: str) -> int:
    """Nível de uma habilidade de prestígio."""
    return u.get("prest", {}).get(chave, 0)


def slots_total(u: dict) -> int:
    return u["slots"] + pl(u, "slot")


def espera(u: dict, base: float) -> float:
    return base * max(0.2, 1 - 0.05 * pl(u, "tempo"))


def custo_sorteio(u: dict) -> float:
    return max(1000.0, lucro_efetivo(u) * 2400 * max(0.2, 1 - 0.04 * pl(u, "sorteio")))


def preco_presente(u: dict, p: dict) -> float:
    return max(100.0, lucro_efetivo(u) * p["seg"])


def custo_casamento(u: dict) -> float:
    return max(50_000.0, lucro_efetivo(u) * 20_000)


def prest_pts(u: dict) -> int:
    return max(0, u["renasc"] - u["prest_gasto"])


def custo_prest(chave: str, lvl: int) -> int:
    return PRESTIGIO[chave][4] * (1 + lvl // 3)


def raridade_idx(nome: str) -> int:
    """Raridade fixa por personagem (sempre a mesma para o mesmo nome)."""
    n = int(hashlib.md5(nome.lower().encode("utf-8")).hexdigest(), 16) % 100
    if n < 50:
        return 0
    if n < 78:
        return 1
    if n < 92:
        return 2
    if n < 98:
        return 3
    return 4


def album_pct(u: dict) -> float:
    return min(100.0, len(u["colecao"]) / ALBUM_META * 100)


def obter_personagem(u: dict, r: dict) -> tuple[bool, int]:
    """Põe a personagem na coleção. Repetida vira fragmentos. Retorna (é nova, fragmentos ganhos)."""
    nome = r["name"]
    ent = u["colecao"].get(nome)
    if ent is None:
        u["colecao"][nome] = {
            "image": r["image"],
            "anime": r.get("anime"),
            "tipo": r.get("tipo", "anime"),
            "qtd": 1,
            "love": 0.0,
        }
        return True, 0
    ent["qtd"] = ent.get("qtd", 1) + 1
    f = RARIDADES[raridade_idx(nome)][3]
    u["fragmentos"] += f
    return False, f


def guardar_main(u: dict, m: dict) -> None:
    """Guarda o progresso de uma Main na coleção (usado ao tirá-la do slot)."""
    ent = u["colecao"].setdefault(
        m["name"], {"image": m["image"], "anime": m.get("anime"), "tipo": "anime", "qtd": 1, "love": 0.0}
    )
    ent["love"] = m["love"]


def equipar_main(u: dict, nome: str) -> str | None:
    """Coloca uma personagem da coleção num slot, com o progresso que ela tinha. Retorna erro ou None."""
    ent = u["colecao"].get(nome)
    if ent is None:
        return "Você não tem essa personagem na coleção."
    if any(m["name"] == nome for m in u["waifus"]):
        return "Ela já está equipada."
    if len(u["waifus"]) >= slots_total(u):
        return (
            f"Seus slots de Main estão cheios ({len(u['waifus'])}/{slots_total(u)}). "
            "Use `/equipar` com o campo `trocar` ou `/remover` (o progresso fica guardado)."
        )
    u["waifus"].append(
        {"name": nome, "image": ent["image"], "anime": ent.get("anime"), "love": ent.get("love", 0.0)}
    )
    u["hist"].setdefault(nome, 1)
    return None


def titulos_do(u: dict) -> dict[str, str]:
    """Todos os títulos que o jogador já desbloqueou (id -> texto)."""
    t = {}
    for cid, emoji, nome, *_ in CONQUISTAS:
        if cid in u["conq"]:
            t[f"c_{cid}"] = f"{emoji} {nome}"
    if u.get("casada"):
        t["casado"] = f"💍 Casado(a) com {u['casada']}"
    pct = album_pct(u)
    for lim, nome in ((25, "📚 Bibliotecário"), (50, "🏛️ Curador"), (100, "🏆 Mestre do Álbum")):
        if pct >= lim:
            t[f"album{lim}"] = nome
    for n, nome in ((3, "🔥 Fênix"), (10, "♾️ Imortal")):
        if u["renasc"] >= n:
            t[f"renasc{n}"] = nome
    if any(raridade_idx(n) == 4 for n in u["colecao"]):
        t["mitico"] = "🟥 Caçador de Míticas"
    return t


def titulo_atual(u: dict) -> str:
    tid = u.get("titulo")
    return titulos_do(u).get(tid, "") if tid else ""


def moldura_info(u: dict) -> tuple[str, int]:
    mid = u.get("moldura")
    if mid in MOLDURAS and mid in u["molduras"]:
        return MOLDURAS[mid][0], MOLDURAS[mid][3]
    return "", ROSA


def _tt(uid: int) -> str:
    u = store.data.get(str(uid))
    t = titulo_atual(u) if u else ""
    return f" _{t}_" if t else ""


def _dur(seg: float) -> str:
    seg = int(max(0, seg))
    d, r = divmod(seg, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}d {h}h {m:02d}min"
    if h:
        return f"{h}h {m:02d}min"
    if m:
        return f"{m}min {r % 60:02d}s"
    return f"{r}s"


def nivel_top(u: dict) -> tuple[str, int]:
    """Personagem de maior nível já alcançado (nome, nível)."""
    if not u["hist"]:
        return "—", 1
    nome, n = max(u["hist"].items(), key=lambda kv: kv[1])
    return nome, n


def stats_texto(u: dict) -> str:
    nome, n = nivel_top(u)
    linhas = [
        f"⏱️ Tempo de jogo: **{_dur(u['t_jogo'])}**",
        f"💵 Dinheiro acumulado: **R$ {fmt(u['tot_money'])}**",
        f"🔥 Maior sequência diária: **{u['max_streak']}** (atual {u['streak']})",
        f"🌹 Encontros: **{u['n_enc']}** • 🎁 Presentes: **{u['n_pres']}**",
        f"⭐ Maior nível: **{nome}** (Nv {n})",
        f"⚔️ Duelos: **{u['vitorias']}**V / **{u['derrotas']}**D",
        f"📚 Coleção: **{len(u['colecao'])}** personagens ({album_pct(u):.0f}% do álbum) • 💠 {u['fragmentos']} fragmentos",
    ]
    if u["hist_renasc"]:
        ult = u["hist_renasc"][-3:]
        lista = ", ".join(f"<t:{int(h['t'])}:d> (R$ {fmt(h['lucro'])}/s)" for h in ult)
        linhas.append(f"🔁 Renascimentos: **{u['renasc']}** — últimos: {lista}")
    else:
        linhas.append("🔁 Renascimentos: **0**")
    return "\n".join(linhas)


def poder(u: dict) -> float:
    """Poder base para duelos (a sorte entra por cima)."""
    n = max((nivel(m["love"])[0] for m in u["waifus"]), default=1)
    return n * 10 + classe_de(u["cp"])[0] * 15 + math.log10(max(lucro_por_segundo(u), 1)) * 10 + u["renasc"] * 5


def req_casamento(u: dict, m: dict) -> list[tuple[str, bool]]:
    n = nivel(m["love"])[0]
    custo_c = custo_casamento(u)
    return [
        (f"Main no nível {CASAMENTO_NIVEL}+ (agora: {n})", n >= CASAMENTO_NIVEL),
        (f"Classe {CLASSES[CASAMENTO_CLASSE][0]} ou melhor", classe_de(u["cp"])[0] >= CASAMENTO_CLASSE),
        (f"{CASAMENTO_ENCONTROS} encontros feitos (agora: {u['n_enc']})", u["n_enc"] >= CASAMENTO_ENCONTROS),
        (f"R$ {fmt(custo_c)} para a cerimônia", u["money"] >= custo_c),
    ]


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.data: dict = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}
        for u in self.data.values():
            migrar(u)
        self.meta: dict = {}
        if META_FILE.exists():
            try:
                self.meta = json.loads(META_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.meta = {}
        self.meta.setdefault("mercado", [])
        self.meta.setdefault("mercado_prox", 1)
        self.meta.setdefault("codigos", {})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
        tmp_m = META_FILE.with_suffix(".tmp")
        tmp_m.write_text(json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_m.replace(META_FILE)

    def user(self, uid: int, criar: bool = False) -> dict | None:
        k = str(uid)
        u = self.data.get(k)
        if u is None and criar:
            u = novo_user()
            self.data[k] = u
        if u is not None:
            acumular(u)
        return u


store = Store(DATA_FILE)




def registrar_tempo(u: dict) -> None:
    """Conta o tempo de jogo: soma o intervalo real entre comandos da mesma sessão."""
    agora = time.time()
    t = u.get("t_jogo", 0.0)
    if not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
        t = 0.0
    ult = u.get("ult_cmd") or 0
    gap = agora - ult
    if ult and 0 < gap <= TEMPO_SESSAO:
        t += gap  # mesma sessão: conta o tempo exato
    else:
        t += TEMPO_INICIO  # sessão nova (ou relógio voltou): só um crédito pequeno
    u["t_jogo"] = float(t)
    u["ult_cmd"] = agora


def marcar(u: dict, interaction) -> None:
    """Guarda onde o player joga (para dar o cargo e avisar no canal)."""
    u["guild"] = interaction.guild_id
    u["channel"] = interaction.channel_id


async def _contar_tempo(interaction: discord.Interaction) -> bool:
    """Registra e persiste o tempo de jogo antes de executar um slash command."""
    try:
        # O dicionário compartilhado precisa do mesmo lock usado pelos comandos.
        # Salvar aqui evita perder o tempo quando o comando seguinte não salva dados.
        async with store.lock:
            u = store.data.get(str(interaction.user.id))
            if u is not None:
                registrar_tempo(u)
                store.save()
    except Exception as exc:  # falha no contador não deve impedir o comando
        print(f"[tempo] Erro ao registrar tempo de jogo: {exc}")
    return True


# ----------------------------------------------------------------------------
# Busca de waifu (AniList + Jikan de reserva)
# ----------------------------------------------------------------------------
ANILIST_QUERY = """
query ($q: String) {
  Page(perPage: 5) {
    characters(search: $q, sort: SEARCH_MATCH) {
      id
      name { full }
      image { large }
      media(perPage: 1, sort: POPULARITY_DESC) { nodes { title { romaji } } }
    }
  }
}
"""


async def _anilist(session: aiohttp.ClientSession, nome: str) -> list[dict]:
    async with session.post(
        "https://graphql.anilist.co",
        json={"query": ANILIST_QUERY, "variables": {"q": nome}},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as r:
        r.raise_for_status()
        data = await r.json()
    out = []
    for c in data["data"]["Page"]["characters"]:
        nodes = c["media"]["nodes"]
        out.append(
            {
                "name": c["name"]["full"],
                "image": c["image"]["large"],
                "anime": nodes[0]["title"]["romaji"] if nodes else None,
            }
        )
    return out


async def _jikan(session: aiohttp.ClientSession, nome: str) -> list[dict]:
    async with session.get(
        "https://api.jikan.moe/v4/characters",
        params={"q": nome, "order_by": "favorites", "sort": "desc", "limit": 5},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as r:
        r.raise_for_status()
        data = await r.json()
    return [
        {"name": c["name"], "image": c["images"]["jpg"]["image_url"], "anime": None}
        for c in data.get("data", [])
    ]


async def _vndb(session: aiohttp.ClientSession, nome: str) -> list[dict]:
    """Personagens de visual novels (VNDB, sem chave de API)."""
    async with session.post(
        "https://api.vndb.org/kana/character",
        json={
            "filters": ["search", "=", nome],
            "fields": "name, image.url, image.sexual, vns.title",
            "results": 5,
        },
        timeout=aiohttp.ClientTimeout(total=8),
    ) as r:
        r.raise_for_status()
        data = await r.json()
    out = []
    for c in data.get("results", []):
        img = c.get("image")
        if not img or img.get("sexual", 0) > 0:  # só imagens seguras
            continue
        vns = c.get("vns") or []
        out.append(
            {
                "name": c["name"],
                "image": img["url"],
                "anime": vns[0]["title"] if vns else "Visual Novel",
                "tipo": "jogo",
            }
        )
    return out


async def _wikidata(session: aiohttp.ClientSession, nome: str) -> list[dict]:
    """Personagens de QUALQUER jogo (Wikidata, sem chave): só os que têm imagem cadastrada."""
    termo = nome.replace("\\", " ").replace('"', " ").strip()
    query = f"""
SELECT ?item ?itemLabel ?image ?gameLabel WHERE {{
  SERVICE wikibase:mwapi {{
    bd:serviceParam wikibase:api "EntitySearch" ;
                    wikibase:endpoint "www.wikidata.org" ;
                    mwapi:search "{termo}" ;
                    mwapi:language "en" ;
                    mwapi:limit "25" .
    ?item wikibase:apiOutputItem mwapi:item .
  }}
  ?item wdt:P31/wdt:P279* wd:Q1569167 ;
        wdt:P18 ?image .
  OPTIONAL {{ ?item wdt:P1441 ?game . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT 20
"""
    async with session.get(
        "https://query.wikidata.org/sparql",
        params={"query": query, "format": "json"},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as r:
        r.raise_for_status()
        data = await r.json(content_type=None)
    out, vistos = [], set()
    for b in data["results"]["bindings"]:
        item = b["item"]["value"]
        if item in vistos:
            continue
        vistos.add(item)
        img = b["image"]["value"].replace("http://", "https://")
        if "Special:FilePath" in img and "width=" not in img:
            img += "?width=500"
        jogo = b.get("gameLabel", {}).get("value")
        out.append(
            {
                "name": b["itemLabel"]["value"],
                "image": img,
                "anime": jogo or "Videogame",
                "tipo": "jogo",
            }
        )
    return out[:5]




async def _giantbomb(session: aiohttp.ClientSession, nome: str) -> list[dict]:
    """Personagens de praticamente todos os jogos (Giant Bomb). Só roda se houver GIANTBOMB_KEY."""
    if not GIANTBOMB_KEY:
        return []
    async with session.get(
        "https://www.giantbomb.com/api/search/",
        params={
            "api_key": GIANTBOMB_KEY,
            "format": "json",
            "query": nome,
            "resources": "character",
            "limit": 5,
            "field_list": "name,image,games",
        },
        timeout=aiohttp.ClientTimeout(total=10),
    ) as r:
        r.raise_for_status()
        data = await r.json()
    out = []
    for c in data.get("results", []):
        img = (c.get("image") or {}).get("super_url") or (c.get("image") or {}).get("medium_url")
        jogos = c.get("games") or []
        out.append(
            {
                "name": c["name"],
                "image": img,
                "anime": jogos[0]["name"] if jogos else "Videogame",
                "tipo": "jogo",
            }
        )
    return out


async def buscar_waifu(session: aiohttp.ClientSession, nome: str) -> list[dict]:
    """Anime/mangá (AniList, com Jikan de reserva) + visual novels (VNDB) + jogos em geral
    (Wikidata e, se houver chave, Giant Bomb). Tudo é buscado de uma vez."""

    async def seguro(corot, rotulo: str) -> list[dict]:
        try:
            return [r for r in await corot if r.get("image")]
        except Exception as e:  # rede fora, rate limit etc.
            print(f"[busca] {rotulo} falhou: {e}")
            return []

    async def anime() -> list[dict]:
        for fonte in (_anilist, _jikan):
            res = await seguro(fonte(session, nome), fonte.__name__)
            if res:
                return [{**r, "tipo": "anime"} for r in res]
        return []

    grupos = await asyncio.gather(
        anime(),
        seguro(_giantbomb(session, nome), "giantbomb"),
        seguro(_vndb(session, nome), "vndb"),
        seguro(_wikidata(session, nome), "wikidata"),
    )
    vistos, out = set(), []
    for grupo in grupos:
        for r in grupo:
            chave = r["name"].lower()
            if chave not in vistos:
                vistos.add(chave)
                out.append(r)
    return out[:15]


# ----------------------------------------------------------------------------
# Bot
# ----------------------------------------------------------------------------
class WaifuBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # necessário para os comandos com prefixo $
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "WaifuDatingBot/2.0"}
        )

        lavahost_key = os.getenv("LAVAHOST_KEY")
        if lavahost_key:
            node = wavelink.Node(
                uri=os.getenv("LAVAHOST_URI", "https://gateway.lavahost.net:443"),
                password=lavahost_key,
            )
            try:
                await wavelink.Pool.connect(nodes=[node], client=self)
                print("Conexão com o Lavalink iniciada.")
            except Exception as exc:
                # A falha do serviço de música não deve derrubar os comandos antigos.
                print(f"[música] Não foi possível conectar ao Lavalink: {exc}")
        else:
            print("[música] LAVAHOST_KEY ausente; comandos de música ficarão indisponíveis.")

        await self.tree.sync()
        if not checar_loop.is_running():
            checar_loop.start()

    async def atualizar_status_voz(self, channel_id: int, status: str) -> bool:
        """Atualiza o status nativo do canal de voz pela API do Discord."""
        if not self.session or not TOKEN:
            return False

        url = f"https://discord.com/api/v10/channels/{channel_id}/voice-status"
        try:
            async with self.session.put(
                url,
                json={"status": status[:500]},
                headers={"Authorization": f"Bot {TOKEN}"},
            ) as response:
                if response.status in (200, 204):
                    print(f"[status de voz] Canal {channel_id}: {status or '(limpo)'}")
                    return True
                detalhe = (await response.text())[:300]
                print(
                    f"[status de voz] Falha HTTP {response.status} "
                    f"no canal {channel_id}: {detalhe}"
                )
        except Exception as exc:
            print(f"[status de voz] Erro ao atualizar canal {channel_id}: {exc}")
        return False

    async def on_wavelink_track_start(self, payload):
        """Mostra título e artista/autor no canal onde o bot está tocando."""
        player = getattr(payload, "player", None)
        canal = getattr(player, "channel", None)
        faixa = getattr(payload, "track", None)
        if canal is None or faixa is None:
            return
        titulo = getattr(faixa, "title", "Música desconhecida")
        autor = getattr(faixa, "author", None)
        texto = f"🎵 {titulo} - {autor}" if autor and autor.lower() not in ("unknown artist", "unknown", "desconhecido") else f"🎵 {titulo}"
        await self.atualizar_status_voz(canal.id, texto)

    async def on_wavelink_track_end(self, payload):
        """Limpa o status quando a faixa termina."""
        player = getattr(payload, "player", None)
        canal = getattr(player, "channel", None)
        if canal is not None:
            await self.atualizar_status_voz(canal.id, "")

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        # Reaplica o status salvo sempre que o bot conecta/reconecta.
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name=PERFIL_BOT.get("status")) if PERFIL_BOT.get("status") else None,
        )
        try:
            usuario = await self.fetch_user(0)
            await usuario.send("🟢 Bot online,Versão {BOT_VERSION}")
        except discord.HTTPException as exc:
            print(f"Erro ao enviar DM: {exc}")
        print(f"Versão {BOT_VERSION}")
        print(f"Online como {self.user}")

    async def on_message(self, message: discord.Message):

        await tratar_prefixo(message)  # $change e $help (ocultos)

bot = WaifuBot()
bot.tree.interaction_check = _contar_tempo  # tempo de jogo em todos os comandos


# último comando de cada (usuário, canal): se repetir o mesmo, edita a mensagem anterior
ultimo: dict[tuple[int, int], dict] = {}


async def responder(interaction: discord.Interaction, cmd: str, *, content=None, embed=None, view=discord.utils.MISSING):
    """Responde ao comando. Se for o mesmo comando seguido, edita a resposta anterior."""
    chave = (interaction.user.id, interaction.channel_id)
    ant = ultimo.get(chave)
    if ant and ant["cmd"] == cmd:
        await interaction.response.defer()
        editou = False
        try:  # 1) pelo token da interação anterior (vale ~15 min)
            await ant["inter"].edit_original_response(content=content, embed=embed, view=view)
            editou = True
        except discord.HTTPException:
            try:  # 2) direto pela mensagem
                canal = bot.get_partial_messageable(interaction.channel_id)
                await canal.get_partial_message(ant["msg_id"]).edit(content=content, embed=embed, view=view)
                editou = True
            except discord.HTTPException:
                pass
        if editou:
            await interaction.delete_original_response()  # some com o "pensando..."
            return
        msg = await interaction.edit_original_response(content=content, embed=embed, view=view)
    else:
        await interaction.response.send_message(content=content, embed=embed, view=view)
        msg = await interaction.original_response()
    ultimo[chave] = {"cmd": cmd, "inter": interaction, "msg_id": msg.id}


async def conceder_deus(uid: int) -> None:
    """Dá o cargo 'Deus do amor' (cria se não existir) e avisa no canal."""
    async with store.lock:
        u = store.data.get(str(uid))
        if not u or u.get("deus"):
            return
        gid, cid = u.get("guild"), u.get("channel")
    guild = bot.get_guild(gid) if gid else None
    if guild is None:
        return
    texto = None
    try:
        member = guild.get_member(uid) or await guild.fetch_member(uid)
        role = discord.utils.get(guild.roles, name=CARGO_NOME)
        if role is None:
            role = await guild.create_role(
                name=CARGO_NOME,
                colour=discord.Colour(ROSA),
                hoist=True,
                reason="Nível máximo de amor",
            )
        await member.add_roles(role, reason="Chegou ao nível máximo de amor")
    except discord.Forbidden:
        async with store.lock:
            avisar = not u.get("aviso_cargo")
            u["aviso_cargo"] = True
            store.save()
        if avisar:
            texto = (
                f"💘 <@{uid}> chegou ao nível máximo, mas não tenho a permissão "
                f"**Gerenciar Cargos** para dar o cargo **{CARGO_NOME}**."
            )
    except discord.HTTPException:
        return
    else:
        async with store.lock:
            u["deus"] = True
            store.save()
        texto = f"👑💘 <@{uid}> alcançou o nível máximo e virou **{CARGO_NOME}**!"
    if texto and cid:
        canal = bot.get_channel(cid)
        if canal:
            await canal.send(texto)


@tasks.loop(seconds=60)
async def checar_loop():
    """A cada minuto vê quem tem uma Main no nível máximo e ainda não ganhou o cargo."""
    async with store.lock:
        pendentes = []
        for uid in list(store.data):
            u = store.user(int(uid))
            if (
                u
                and not u.get("deus")
                and u.get("guild")
                and any(m["love"] >= limiar(NIVEL_MAX) for m in u["waifus"])
            ):
                pendentes.append(int(uid))
    for uid in pendentes:
        await conceder_deus(uid)


class BuscaView(discord.ui.View):
    def __init__(self, uid: int, resultados: list[dict]):
        super().__init__(timeout=180)
        self.uid = uid
        self.resultados = resultados
        self.i = 0

    def embed(self) -> discord.Embed:
        r = self.resultados[self.i]
        e = discord.Embed(title=r["name"], color=ROSA)
        if r["anime"]:
            e.description = f"{'🎮' if r.get('tipo') == 'jogo' else '📺'} {r['anime']}"
        e.set_image(url=r["image"])
        e.set_footer(text=f"Resultado {self.i + 1}/{len(self.resultados)}")
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.uid:
            await interaction.response.send_message("Essa busca é de outra pessoa.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def anterior(self, interaction: discord.Interaction, _):
        self.i = (self.i - 1) % len(self.resultados)
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="💖 Escolher", style=discord.ButtonStyle.success)
    async def escolher(self, interaction: discord.Interaction, _):
        r = self.resultados[self.i]
        async with store.lock:
            u = store.user(self.uid, criar=True)
            marcar(u, interaction)
            if any(m["name"] == r["name"] for m in u["waifus"]):
                await interaction.response.send_message(
                    f"**{r['name']}** já é uma das suas Mains.", ephemeral=True
                )
                return
            nova = r["name"] not in u["colecao"]
            if nova:
                obter_personagem(u, r)
            erro = equipar_main(u, r["name"])
            ra = RARIDADES[raridade_idx(r["name"])]
            if erro:  # slots cheios: fica na coleção, sem perder nada
                texto = (
                    f"📚 **{r['name']}** ({ra[1]} {ra[0]}) {'entrou na' if nova else 'está na'} sua coleção. "
                    f"{erro}"
                )
            else:
                logar(u, f"💞 {r['name']} virou Main")
                texto = (
                    f"💞 **{r['name']}** ({ra[1]} {ra[0]}) agora é uma das suas Mains "
                    f"({len(u['waifus'])}/{slots_total(u)})! Use `/perfil`, `/loja` e `/comprar`."
                )
            store.save()
        self.stop()
        await interaction.response.edit_message(content=texto, embed=self.embed(), view=None)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def proxima(self, interaction: discord.Interaction, _):
        self.i = (self.i + 1) % len(self.resultados)
        await interaction.response.edit_message(embed=self.embed(), view=self)


NAO_COMECOU = "Você ainda não tem nenhuma Main. Use `/waifu nome` (ou `/equipar` se já tem coleção) 💕"


async def jogador_ativo(interaction: discord.Interaction) -> dict | None:
    """Devolve os dados do jogador (já atualizados) ou avisa que ele ainda não começou.

    Deve ser chamada DENTRO de `async with store.lock:`. Retorna None quando o
    jogador não existe ou não tem nenhuma Main (a resposta já foi enviada).
    """
    u = store.user(interaction.user.id)
    if u is None or not u["waifus"]:
        await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
        return None
    return u


async def iniciar_comando(interaction: discord.Interaction) -> tuple[dict, str | None] | None:
    """Padrão dos comandos de consulta: valida o jogador, pega o lock, marca onde ele joga,
    junta avisos/eventos e salva. Retorna (dados, aviso) ou None se o jogador não começou."""
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return None
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    return u, aviso


@bot.tree.command(name="waifu", description="Busca uma personagem (anime ou jogo) e escolhe como Main")
@app_commands.describe(nome="Nome da personagem")
async def waifu(interaction: discord.Interaction, nome: str):
    await interaction.response.defer()
    resultados = await buscar_waifu(bot.session, nome)
    if not resultados:
        await interaction.followup.send("Não achei ninguém com esse nome 😢")
        return
    view = BuscaView(interaction.user.id, resultados)
    await interaction.followup.send(embed=view.embed(), view=view)


def barra(atual: float, minimo: float, alvo: float | None) -> str:
    if alvo is None:
        return "▰" * 10 + " MAX"
    frac = max(0.0, min(1.0, (atual - minimo) / (alvo - minimo)))
    cheio = int(frac * 10)
    return "▰" * cheio + "▱" * (10 - cheio) + f" {fmt(atual)}/{fmt(alvo)}"


def _tempo(seg: float) -> str:
    seg = int(max(0, seg))
    return f"{seg // 60}min{seg % 60:02d}s" if seg >= 60 else f"{seg}s"

@bot.tree.command(name="status", description="Altera e salva o status de atividade do bot")
@app_commands.describe(texto="Texto que aparecerá como status do bot")
async def status(interaction: discord.Interaction, texto: str):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Você não pode usar esse comando.", ephemeral=True)
        return
    texto = texto.strip()[:128]
    if not texto:
        await interaction.response.send_message("O status não pode ficar vazio.", ephemeral=True)
        return
    PERFIL_BOT["status"] = texto
    try:
        salvar_perfil_bot()
        await bot.change_presence(status=discord.Status.online, activity=discord.Game(name=texto))
    except OSError as exc:
        await interaction.response.send_message(f"❌ Não consegui salvar a configuração: {exc}", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Status alterado e salvo: **{texto}**\nEle será reaplicado quando o bot reiniciar.")

@bot.tree.command(name="bio", description="Salva a bio/descrição informativa do bot")
@app_commands.describe(texto="Bio que você quer guardar para o bot")
async def bio_bot(interaction: discord.Interaction, texto: str):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Você não pode usar esse comando.", ephemeral=True)
        return
    texto = texto.strip()[:1000]
    PERFIL_BOT["bio"] = texto
    try:
        salvar_perfil_bot()
    except OSError as exc:
        await interaction.response.send_message(f"❌ Não consegui salvar a bio: {exc}", ephemeral=True)
        return
    await interaction.response.send_message(
        "✅ Bio salva no arquivo `bot_profile.json`.\n"
        "Aviso: a API oficial de bots do Discord não permite alterar automaticamente o campo Sobre Mim do perfil; "
        "essa bio fica guardada na configuração do bot, não muda esse campo do Discord."
    )

@bot.tree.command(name="perfilbot", description="Mostra as configurações salvas do perfil do bot")
async def perfilbot(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Você não pode usar esse comando.", ephemeral=True)
        return
    bio = PERFIL_BOT.get("bio") or "(nenhuma bio salva)"
    status_atual = PERFIL_BOT.get("status") or "(sem status de atividade)"
    await interaction.response.send_message(
        f"**Status salvo:** {status_atual}\n**Bio salva:** {bio}", ephemeral=True
    )

@bot.tree.command(name="perfil", description="Mostra seu dinheiro, classe e suas Mains")
async def perfil(interaction: discord.Interaction):
    ini = await iniciar_comando(interaction)
    if ini is None:
        return
    u, aviso = ini
    rps_bruto = lucro_por_segundo(u)
    pen = penalidade(rps_bruto)
    _, c_nome, c_emoji, c_bonus, c_prox = classe_de(u["cp"])
    mold, cor_m = moldura_info(u)
    tit = titulo_atual(u)
    nome_user = interaction.user.display_name
    linhas_desc = [
        f"{c_emoji} **{c_nome}** • 💞 {len(u['waifus'])} Main(s) • 💰 R$ {fmt(u['money'])}",
    ]
    if tit:
        linhas_desc.insert(0, f"🏷️ {tit}")
    e = discord.Embed(
        title=f"{mold} 💞 Perfil de {nome_user}!".strip(),
        description="\n".join(linhas_desc),
        color=cor_m,
        timestamp=discord.utils.utcnow(),
    )
    e.set_author(name=nome_user, icon_url=interaction.user.display_avatar.url)
    e.set_thumbnail(url=u["waifus"][0]["image"])  # Main principal, em tamanho pequeno
    e.set_footer(
        text=f"💖 Simulador de namoro • Página 1/2 • v{BOT_VERSION}",
        icon_url=interaction.user.display_avatar.url,
    )
    e.add_field(name="💰 Dinheiro", value=f"R$ {fmt(u['money'])}", inline=True)
    e.add_field(name="📈 Lucro", value=f"R$ {fmt(lucro_efetivo(u))}/s", inline=True)
    e.add_field(
        name="🏆 Classe",
        value=(
            f"{c_emoji} **{c_nome}** (+{c_bonus}%)\n"
            f"{fmt(u['cp'])} pts" + (f" • próximo: {fmt(c_prox)}" if c_prox else " • MAX")
        ),
        inline=True,
    )
    por_main = amor_efetivo(u) / len(u["waifus"])
    e.add_field(
        name=f"👥 Mains ({len(u['waifus'])}/{slots_total(u)} slots)",
        value="\n".join(
            _linha_main(m, por_main, u.get("deus")) for m in u["waifus"]
        ),
        inline=False,
    )
    e.add_field(
        name="💓 Ganho de amor",
        value=(
            f"{fmt(amor_efetivo(u), 2)} pts/s no total, dividido entre as Mains "
            f"(penalidade do lucro: -{fmt(pen, 2)})"
        ),
        inline=False,
    )
    e.add_field(
        name="✨ Bônus permanentes",
        value=(
            f"💰 +{u['b_lucro']}% dinheiro • ❤️ +{u['b_amor']}% amor • 🏆 +{c_bonus}% da classe"
            + (f" • 🔁 +{u['renasc'] * BONUS_RENASCER}% ({u['renasc']}x renascido)" if u["renasc"] else "")
        ),
        inline=False,
    )
    agora = time.time()
    ativos = [b for b in u["buffs"] if b["ate"] > agora]
    if ativos:
        e.add_field(
            name="⏳ Efeitos ativos",
            value="\n".join(
                f"{'📈' if b['t'] == 'lucro' else '💘'} {b['t'].capitalize()} x{fmt(b['m'])} "
                f"({_tempo(b['ate'] - agora)})"
                for b in ativos
            ),
            inline=False,
        )
    # Página 2: itens menos essenciais (estatísticas e upgrades)
    e2 = discord.Embed(
        title=f"{mold} 📊 Detalhes de {nome_user}".strip(),
        description="Estatísticas e upgrades — o resto do perfil está na página 1.",
        color=cor_m,
        timestamp=discord.utils.utcnow(),
    )
    e2.set_thumbnail(url=interaction.user.display_avatar.url)
    e2.add_field(name="📊 Estatísticas", value=stats_texto(u)[:1024], inline=False)
    lista = "\n".join(
        f"{ITEMS[k]['emoji']} {ITEMS[k]['nome']} x{q}" for k, q in u["items"].items() if q and k in ITEMS
    )
    e2.add_field(name="🛍️ Upgrades", value=lista[:1024] or "Nenhum upgrade comprado ainda.", inline=False)
    e2.set_footer(
        text=f"💖 Simulador de namoro • Página 2/2 • v{BOT_VERSION}",
        icon_url=interaction.user.display_avatar.url,
    )
    await responder(
        interaction, "perfil", content=aviso, embed=e, view=PerfilView(interaction.user.id, e, e2)
    )


class PerfilView(discord.ui.View):
    """Botões para alternar entre a página 1 (essencial) e a 2 (estatísticas/upgrades)."""

    def __init__(self, uid: int, pag1: discord.Embed, pag2: discord.Embed):
        super().__init__(timeout=180)
        self.uid = uid
        self.paginas = (pag1, pag2)
        self.atual = 0
        self._atualizar_botoes()

    def _atualizar_botoes(self) -> None:
        self.anterior.disabled = self.atual == 0
        self.proxima.disabled = self.atual == len(self.paginas) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.uid:
            await interaction.response.send_message("Esse perfil não é seu. Use `/perfil`.", ephemeral=True)
            return False
        return True

    async def _ir(self, interaction: discord.Interaction, destino: int) -> None:
        self.atual = destino
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.paginas[self.atual], view=self)

    @discord.ui.button(label="◀ Página 1", style=discord.ButtonStyle.secondary)
    async def anterior(self, interaction: discord.Interaction, _):
        await self._ir(interaction, 0)

    @discord.ui.button(label="Página 2 ▶", style=discord.ButtonStyle.primary)
    async def proxima(self, interaction: discord.Interaction, _):
        await self._ir(interaction, 1)


def _linha_main(m: dict, por_seg: float, deus: bool) -> str:
    n, nome_n, prox = nivel(m["love"])
    return (
        f"**{m['name']}** — Nv {n}/{NIVEL_MAX} **{nome_n}**{' 👑' if deus and n == NIVEL_MAX else ''} "
        f"(+{fmt(por_seg, 2)}/s)\n{barra(m['love'], limiar(n), prox)}"
    )


@bot.tree.command(name="classe", description="Mostra as classes de Bronze a Diamante e seu progresso")
async def classe(interaction: discord.Interaction):
    ini = await iniciar_comando(interaction)
    if ini is None:
        return
    u, aviso = ini
    idx, nome, emoji, bonus, prox = classe_de(u["cp"])
    linhas = []
    for i, (n, em, minimo, b) in enumerate(CLASSES):
        marca = "➡️ " if i == idx else ("✅ " if i < idx else "🔒 ")
        linhas.append(f"{marca}{em} **{n}** — {fmt(minimo)} pts • +{b}% dinheiro e amor")
    e = discord.Embed(title=f"🏆 Sua classe: {emoji} {nome}", description="\n".join(linhas), color=ROSA)
    atual_min = CLASSES[idx][2]
    e.add_field(
        name="Progresso",
        value=f"{barra(u['cp'], atual_min, prox)}" if prox else f"{fmt(u['cp'])} pts • MAX",
        inline=False,
    )
    e.set_footer(
        text="Pontos de classe: ao subir uma Main para o nível N você ganha N pontos "
        "(uma vez por nível de cada personagem)."
    )
    await responder(interaction, "classe", content=aviso, embed=e)


@bot.tree.command(name="loja", description="Mostra os upgrades disponíveis")
async def loja(interaction: discord.Interaction):
    ini = await iniciar_comando(interaction)
    if ini is None:
        return
    u, aviso = ini
    e = discord.Embed(title="🛒 Loja", description=f"Seu saldo: **R$ {fmt(u['money'])}**", color=ROSA)
    for tipo, titulo in (("lucro", "📈 Lucro"), ("amor", "❤️ Relacionamento")):
        linhas = []
        for k, it in ITEMS.items():
            if it["tipo"] != tipo:
                continue
            possui = u["items"].get(k, 0)
            efeito = (
                f"+R$ {fmt(it['valor'])}/s" if tipo == "lucro" else f"+{fmt(it['valor'])} pts/s"
            )
            linhas.append(
                f"{it['emoji']} **{it['nome']}** (`{k}`) — {efeito}\n"
                f"R$ {fmt(custo(k, possui, u))} • você tem {possui}"
            )
        for i in range(0, len(linhas), 5):  # campos têm limite de 1024 caracteres
            e.add_field(
                name=titulo if i == 0 else "\u200b",
                value="\n".join(linhas[i : i + 5]),
                inline=False,
            )
    e.set_footer(text="Lucro muito alto reduz um pouquinho o ganho de relacionamento.")
    await responder(interaction, "loja", content=aviso, embed=e)


@bot.tree.command(name="comprar", description="Compra um upgrade")
@app_commands.describe(item="O que comprar", quantidade="Quantas unidades (padrão 1)")
@app_commands.choices(
    item=[
        app_commands.Choice(name=f"{v['emoji']} {v['nome']}", value=k)
        for k, v in list(ITEMS.items())[:25]
    ]
)
async def comprar(
    interaction: discord.Interaction,
    item: app_commands.Choice[str],
    quantidade: app_commands.Range[int, 1, 100] = 1,
):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        k = item.value
        possui = u["items"].get(k, 0)
        total = sum(custo(k, possui + i, u) for i in range(quantidade))
        if u["money"] < total:
            falta = total - u["money"]
            await interaction.response.send_message(
                f"Faltam R$ {fmt(falta)} para comprar {quantidade}x {ITEMS[k]['nome']} "
                f"(custa R$ {fmt(total)}).",
                ephemeral=True,
            )
            return
        u["money"] = round(u["money"] - total, 2)
        u["items"][k] = possui + quantidade
        logar(u, f"🛍️ Comprou {quantidade}x {ITEMS[k]['nome']} (R$ {fmt(total)})")
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    it = ITEMS[k]
    await responder(
        interaction,
        "comprar",
        content=(
            f"{it['emoji']} Comprou {quantidade}x **{it['nome']}** por R$ {fmt(total)}!\n"
            f"Lucro: R$ {fmt(lucro_efetivo(u))}/s • "
            f"Amor: {fmt(amor_efetivo(u), 2)} pts/s (dividido entre as Mains)"
            + (f"\n{aviso}" if aviso else "")
        ),
    )




@bot.tree.command(name="diario", description="Resgata sua recompensa diária (quanto mais dias seguidos, melhor)")
async def diario(interaction: discord.Interaction):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        agora = time.time()
        passou = agora - u["diario"]
        if passou < DIARIO_ESPERA:
            falta = DIARIO_ESPERA - passou
            await interaction.response.send_message(
                f"Você já resgatou hoje. Volte em {int(falta // 3600)}h{int(falta % 3600 // 60):02d}min ⏰",
                ephemeral=True,
            )
            return
        u["streak"] = u["streak"] + 1 if passou <= DIARIO_LIMITE and u["diario"] else 1
        u["diario"] = agora
        u["max_streak"] = max(u["max_streak"], u["streak"])
        logar(u, f"🎁 Diário resgatado (sequência de {u['streak']})")
        bonus = 1 + 0.10 * min(u["streak"], 10)
        din = max(100.0, lucro_efetivo(u) * 600 * bonus)
        amor_cada = amor_efetivo(u) / len(u["waifus"]) * 300 * bonus
        add_money(u, din)
        for m in u["waifus"]:
            m["love"] += amor_cada
        processar_niveis(u)
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    await responder(
        interaction,
        "diario",
        content=(
            f"🎁 Recompensa diária (sequência: **{u['streak']}** 🔥)\n"
            f"💰 +R$ {fmt(din)}\n❤️ +{fmt(amor_cada, 2)} pts para cada Main"
            + (f"\n{aviso}" if aviso else "")
        ),
    )


class RemoverView(discord.ui.View):
    def __init__(self, uid: int, nome: str):
        super().__init__(timeout=30)
        self.uid = uid
        self.nome = nome

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.uid

    @discord.ui.button(label="Sim, remover", style=discord.ButtonStyle.danger)
    async def sim(self, interaction: discord.Interaction, _):
        async with store.lock:
            u = store.user(self.uid)
            antes = len(u["waifus"]) if u else 0
            if u:
                for m in u["waifus"]:
                    if m["name"] == self.nome:
                        guardar_main(u, m)  # o progresso fica guardado na coleção
                u["waifus"] = [m for m in u["waifus"] if m["name"] != self.nome]
                store.save()
            removeu = u is not None and len(u["waifus"]) < antes
        self.stop()
        await interaction.response.edit_message(
            content=f"📦 **{self.nome}** saiu do slot e foi para a coleção (progresso guardado; use `/equipar`)."
            if removeu
            else "Não achei essa Main.",
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def nao(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)


@bot.tree.command(name="remover", description="Tira uma Main do slot (ela vai para a coleção com o progresso)")
@app_commands.describe(nome="Qual Main remover")
async def remover(interaction: discord.Interaction, nome: str):
    async with store.lock:
        u = store.user(interaction.user.id)
        existe = u is not None and any(m["name"] == nome for m in u["waifus"])
    if not existe:
        await interaction.response.send_message("Você não tem essa Main.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"Tirar **{nome}** do slot? Ela vai para a coleção e o progresso fica guardado "
        "(volte com `/equipar`). Enquanto estiver guardada, ela não gera amor.",
        view=RemoverView(interaction.user.id, nome),
        ephemeral=True,
    )


async def remover_auto(interaction: discord.Interaction, atual: str):
    u = store.data.get(str(interaction.user.id))
    if not u:
        return []
    return [
        app_commands.Choice(name=m["name"][:100], value=m["name"][:100])
        for m in u["waifus"]
        if atual.lower() in m["name"].lower()
    ][:25]


remover.autocomplete("nome")(remover_auto)


class ResetView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=30)
        self.uid = uid

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.uid

    @discord.ui.button(label="Sim, recomeçar", style=discord.ButtonStyle.danger)
    async def sim(self, interaction: discord.Interaction, _):
        async with store.lock:
            store.data.pop(str(self.uid), None)
            store.meta["mercado"] = [a for a in store.meta["mercado"] if a["vendedor"] != self.uid]
            store.save()
        self.stop()
        await interaction.response.edit_message(content="Progresso apagado 💔", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def nao(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)


@bot.tree.command(name="resetar", description="Apaga seu progresso e recomeça")
async def resetar(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Tem certeza? Isso apaga tudo.", view=ResetView(interaction.user.id), ephemeral=True
    )


# ----------------------------------------------------------------------------
# Novos mecanismos: trabalhar, encontro, presentear, renascer, conquistas, ranking
# ----------------------------------------------------------------------------
@bot.tree.command(name="trabalhar", description="Faz um bico rápido e ganha dinheiro (a cada 5 minutos)")
async def trabalhar(interaction: discord.Interaction):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        agora = time.time()
        falta = u["t_trab"] + espera(u, TRABALHO_ESPERA) - agora
        if falta > 0:
            await interaction.response.send_message(f"Você está cansado. Volte em {_tempo(falta)} ⏰", ephemeral=True)
            return
        u["t_trab"] = agora
        ganho = max(20.0, lucro_efetivo(u) * 300 * random.uniform(0.8, 1.5))
        sorte = random.random()
        if sorte < 0.10:
            ganho /= 3
            extra = " (dia fraco 😅)"
        elif sorte > 0.92:
            ganho *= 2
            extra = " (rolou uma gorjeta! 🤑)"
        else:
            extra = ""
        add_money(u, ganho)
        logar(u, f"🧰 Trabalhou e ganhou R$ {fmt(ganho)}")
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    await responder(
        interaction,
        "trabalhar",
        content=f"🧰 Você trabalhou e ganhou **R$ {fmt(ganho)}**{extra}" + (f"\n{aviso}" if aviso else ""),
    )


@bot.tree.command(name="encontro", description="Leva uma Main para sair: paga dinheiro e ganha amor (a cada 2 horas)")
@app_commands.describe(nome="Qual Main levar para sair")
async def encontro(interaction: discord.Interaction, nome: str):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        m = next((m for m in u["waifus"] if m["name"] == nome), None)
        if m is None:
            await interaction.response.send_message("Você não tem essa Main.", ephemeral=True)
            return
        agora = time.time()
        falta = u["t_enc"] + espera(u, ENCONTRO_ESPERA) - agora
        if falta > 0:
            await interaction.response.send_message(
                f"Vocês já saíram há pouco. Volte em {_tempo(falta)} ⏰", ephemeral=True
            )
            return
        n, _, prox = nivel(m["love"])
        if prox is None:
            await interaction.response.send_message(f"**{m['name']}** já está no amor máximo 💖", ephemeral=True)
            return
        preco = max(100.0, lucro_efetivo(u) * 900)
        if u["money"] < preco:
            await interaction.response.send_message(
                f"Um encontro custa R$ {fmt(preco)} e você tem R$ {fmt(u['money'])}.", ephemeral=True
            )
            return
        u["money"] = round(u["money"] - preco, 2)
        u["t_enc"] = agora
        ganho = (prox - limiar(n)) * random.uniform(0.06, 0.12)
        m["love"] += ganho
        u["n_enc"] += 1
        logar(u, f"🌹 Encontro com {nome} (-R$ {fmt(preco)}, +{fmt(ganho)} pts)")
        processar_niveis(u)
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    await responder(
        interaction,
        "encontro",
        content=(
            f"🌹 Encontro com **{nome}**! Você gastou R$ {fmt(preco)} e ganhou **+{fmt(ganho)} pts** de amor"
            + (f"\n{aviso}" if aviso else "")
        ),
    )


encontro.autocomplete("nome")(remover_auto)


@bot.tree.command(name="presentear", description="Gasta dinheiro para dar pontos de amor a uma Main")
@app_commands.describe(nome="Qual Main presentear", valor="Quanto dinheiro gastar")
async def presentear(interaction: discord.Interaction, nome: str, valor: app_commands.Range[float, 1]):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        m = next((m for m in u["waifus"] if m["name"] == nome), None)
        if m is None:
            await interaction.response.send_message("Você não tem essa Main.", ephemeral=True)
            return
        valor = round(valor, 2)
        if u["money"] < valor:
            await interaction.response.send_message(
                f"Você só tem R$ {fmt(u['money'])}.", ephemeral=True
            )
            return
        if nivel(m["love"])[2] is None:
            await interaction.response.send_message(f"**{m['name']}** já está no amor máximo 💖", ephemeral=True)
            return
        pts = valor**PRESENTE_EXPOENTE / 10
        u["money"] = round(u["money"] - valor, 2)
        m["love"] += pts
        u["n_pres"] += 1
        logar(u, f"🎁 Presenteou {nome} com R$ {fmt(valor)} (+{fmt(pts)} pts)")
        processar_niveis(u)
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    await responder(
        interaction,
        "presentear",
        content=(
            f"🎁 **{nome}** adorou o presente de R$ {fmt(valor)}! **+{fmt(pts)} pts** de amor"
            + (f"\n{aviso}" if aviso else "")
        ),
    )


presentear.autocomplete("nome")(remover_auto)


class RenascerView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=45)
        self.uid = uid

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.uid

    @discord.ui.button(label="Sim, renascer", style=discord.ButtonStyle.danger)
    async def sim(self, interaction: discord.Interaction, _):
        async with store.lock:
            u = store.user(self.uid)
            if u is None or lucro_por_segundo(u) < RENASCER_MIN:
                self.stop()
                await interaction.response.edit_message(content="Você não pode mais renascer agora.", view=None)
                return
            u["hist_renasc"].append({"t": time.time(), "lucro": lucro_por_segundo(u), "cp": u["cp"]})
            u["money"] = 0.0
            u["items"] = {}
            u["buffs"] = []
            u["renasc"] += 1
            logar(u, f"🔁 Renasceu ({u['renasc']}x) e ganhou 1 ponto de prestígio")
            processar_niveis(u)
            store.save()
            n = u["renasc"]
        self.stop()
        await interaction.response.edit_message(
            content=f"🔁 Você renasceu! (**{n}x**) Agora tem **+{n * BONUS_RENASCER}%** permanente de dinheiro e amor e 1 ponto de prestígio (`/prestigio`).",
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def nao(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)


@bot.tree.command(name="renascer", description="Zera dinheiro e upgrades em troca de +10% permanente de dinheiro e amor")
async def renascer(interaction: discord.Interaction):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        lucro = lucro_por_segundo(u)
        renasc = u["renasc"]
    if lucro < RENASCER_MIN:
        await interaction.response.send_message(
            f"Para renascer você precisa de pelo menos **R$ {fmt(RENASCER_MIN)}/s** de lucro bruto "
            f"(você tem R$ {fmt(lucro)}/s).",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        f"Renascer vai **zerar seu dinheiro e seus upgrades**, mas você mantém Mains, níveis, classe, "
        f"conquistas, coleção e ganha **+{BONUS_RENASCER}%** permanente de dinheiro e amor "
        f"(você já renasceu {renasc}x). Confirmar?",
        view=RenascerView(interaction.user.id),
        ephemeral=True,
    )


@bot.tree.command(name="conquistas", description="Mostra suas conquistas e recompensas")
async def conquistas(interaction: discord.Interaction):
    ini = await iniciar_comando(interaction)
    if ini is None:
        return
    u, aviso = ini
    linhas = []
    for cid, emoji, nome, desc, _, (tipo, v) in CONQUISTAS:
        feito = cid in u["conq"]
        rec = f"{fmt(v)}s de lucro em dinheiro" if tipo == "dinheiro" else f"+{v}% {'dinheiro' if tipo == 'lucro' else 'amor'}"
        linhas.append(f"{'✅' if feito else '🔒'} {emoji} **{nome}** — {desc} • _{rec}_")
    e = discord.Embed(
        title=f"🏅 Conquistas ({len(u['conq'])}/{len(CONQUISTAS)})",
        description="\n".join(linhas),
        color=ROSA,
    )
    await responder(interaction, "conquistas", content=aviso, embed=e)


RANKINGS = {
    "cp": ("🏆 Pontos de classe", lambda u: u["cp"], fmt),
    "money": ("💰 Dinheiro", lambda u: u["money"], fmt),
    "lucro": ("📈 Lucro/s", lambda u: lucro_efetivo(u), fmt),
    "renasc": ("🔁 Renascimentos", lambda u: u["renasc"], fmt),
    "tot_money": ("💵 Dinheiro acumulado", lambda u: u["tot_money"], fmt),
    "tempo": ("⏱️ Tempo de jogo", lambda u: u["t_jogo"], _dur),
    "streak": ("🔥 Maior sequência diária", lambda u: u["max_streak"], fmt),
    "encontros": ("🌹 Encontros", lambda u: u["n_enc"], fmt),
    "presentes": ("🎁 Presentes", lambda u: u["n_pres"], fmt),
    "nivel": ("⭐ Maior nível de uma Main", lambda u: nivel_top(u)[1], fmt),
    "vitorias": ("⚔️ Vitórias em duelos", lambda u: u["vitorias"], fmt),
    "colecao": ("📚 Personagens na coleção", lambda u: len(u["colecao"]), fmt),
}


@bot.tree.command(name="ranking", description="Top 10 jogadores")
@app_commands.describe(tipo="O que ordenar (padrão: pontos de classe)")
@app_commands.choices(tipo=[app_commands.Choice(name=v[0], value=k) for k, v in RANKINGS.items()])
async def ranking(interaction: discord.Interaction, tipo: app_commands.Choice[str] | None = None):
    chave = tipo.value if tipo else "cp"
    titulo, fn, formato = RANKINGS[chave]
    async with store.lock:
        placar = []
        for uid in list(store.data):
            u = store.user(int(uid))
            if u and u["waifus"]:
                placar.append((int(uid), fn(u)))
    placar.sort(key=lambda x: x[1], reverse=True)
    if not placar:
        await interaction.response.send_message("Ainda não tem ninguém no ranking.", ephemeral=True)
        return
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = [
        f"{medalhas[i] if i < 3 else f'`{i + 1}.`'} <@{uid}>{_tt(uid)} — {formato(v)}"
        for i, (uid, v) in enumerate(placar[:10])
    ]
    pos = next((i + 1 for i, (uid, _) in enumerate(placar) if uid == interaction.user.id), None)
    e = discord.Embed(title=f"Ranking — {titulo}", description="\n".join(linhas), color=ROSA)
    if pos and pos > 10:
        e.set_footer(text=f"Você está em {pos}º lugar")
    await interaction.response.send_message(embed=e)


# ----------------------------------------------------------------------------
# Novos comandos: casal, presentes, casamento, títulos, prestígio, duelo, sorteio,
# coleção, equipar, molduras, mercado, códigos e histórico
# ----------------------------------------------------------------------------
class ConfirmarView(discord.ui.View):
    """Botão genérico de confirmação: chama `acao(interaction)` se o dono confirmar."""

    def __init__(self, uid: int, acao, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.uid = uid
        self.acao = acao

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.uid

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def ok(self, interaction: discord.Interaction, _):
        self.stop()
        await self.acao(interaction)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def nao(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", embed=None, view=None)


def eh_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ADMIN_IDS


async def so_admin(interaction: discord.Interaction) -> bool:
    if eh_admin(interaction):
        return True
    await interaction.response.send_message("❌ Só administradores do bot podem usar isso.", ephemeral=True)
    return False


# ---- /casal -----------------------------------------------------------------
@bot.tree.command(name="casal", description="Mostra o cartão de casal de uma Main")
@app_commands.describe(nome="Qual Main (padrão: a primeira)")
async def casal(interaction: discord.Interaction, nome: str | None = None):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        m = next((x for x in u["waifus"] if x["name"] == nome), None) if nome else u["waifus"][0]
        if m is None:
            await interaction.response.send_message("Você não tem essa Main.", ephemeral=True)
            return
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    n, nome_n, prox = nivel(m["love"])
    r_nome, r_emoji, r_cor, _ = RARIDADES[raridade_idx(m["name"])]
    mold, cor = moldura_info(u)
    casados = u.get("casada") == m["name"]
    por_seg = amor_efetivo(u) / len(u["waifus"])
    e = discord.Embed(
        title=f"{mold} 💞 {m['name']} {mold}".strip(),
        description=f"{'💍 **Casados**' if casados else f'**{nome_n}**'} com {interaction.user.display_name}",
        color=cor if mold else r_cor,
    )
    e.set_image(url=m["image"])
    e.add_field(name="💖 Nível", value=f"{n}/{NIVEL_MAX}", inline=True)
    e.add_field(name="✨ Raridade", value=f"{r_emoji} {r_nome}", inline=True)
    e.add_field(name="📺 Origem", value=m.get("anime") or "—", inline=True)
    e.add_field(
        name="💓 Afinidade",
        value=f"{barra(m['love'], limiar(n), prox)}\nTotal: {fmt(m['love'])} pts • +{fmt(por_seg, 2)}/s",
        inline=False,
    )
    t = titulo_atual(u)
    if t:
        e.add_field(name="🏷️ Título", value=t, inline=False)
    await responder(interaction, "casal", content=aviso, embed=e)


casal.autocomplete("nome")(remover_auto)


# ---- /presentes -------------------------------------------------------------
def _efeito_presente(p: dict) -> str:
    partes = [f"+{int(p['amor'] * 100)}% do nível em amor"]
    if "buff" in p:
        tipo, mlt, seg = p["buff"]
        partes.append(f"{'amor' if tipo == 'amor' else 'lucro'} x{fmt(mlt)} por {seg // 60}min")
    if "bonus" in p:
        partes.append(f"+{p['bonus']}% de amor permanente (máx. {p['limite']}x)")
    return " • ".join(partes)


@bot.tree.command(name="presentes", description="Catálogo de presentes com efeitos diferentes (escolha um para dar)")
@app_commands.describe(item="Presente para comprar e dar (vazio = ver o catálogo)", nome="Qual Main presentear")
@app_commands.choices(
    item=[app_commands.Choice(name=f"{p['emoji']} {p['nome']}", value=k) for k, p in PRESENTES.items()]
)
async def presentes(
    interaction: discord.Interaction,
    item: app_commands.Choice[str] | None = None,
    nome: str | None = None,
):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        marcar(u, interaction)
        if item is None:
            aviso = coletar(u)
            store.save()
            e = discord.Embed(
                title="🎁 Catálogo de presentes",
                description=f"Seu saldo: **R$ {fmt(u['money'])}**\nUse `/presentes item:... nome:...`",
                color=ROSA,
            )
            for k, p in PRESENTES.items():
                e.add_field(
                    name=f"{p['emoji']} {p['nome']} — R$ {fmt(preco_presente(u, p))}",
                    value=_efeito_presente(p),
                    inline=False,
                )
            await responder(interaction, "presentes", content=aviso, embed=e)
            return
        p = PRESENTES[item.value]
        m = next((x for x in u["waifus"] if x["name"] == nome), None) if nome else u["waifus"][0]
        if m is None:
            await interaction.response.send_message("Você não tem essa Main.", ephemeral=True)
            return
        n, _, prox = nivel(m["love"])
        if prox is None:
            await interaction.response.send_message(f"**{m['name']}** já está no amor máximo 💖", ephemeral=True)
            return
        preco = preco_presente(u, p)
        if u["money"] < preco:
            await interaction.response.send_message(
                f"{p['emoji']} {p['nome']} custa R$ {fmt(preco)} e você tem R$ {fmt(u['money'])}.", ephemeral=True
            )
            return
        u["money"] = round(u["money"] - preco, 2)
        ganho = (prox - limiar(n)) * p["amor"]
        m["love"] += ganho
        extras = []
        if "buff" in p:
            tipo, mlt, seg = p["buff"]
            _buff(u, tipo, mlt, seg)
            extras.append(f"{'💘 amor' if tipo == 'amor' else '📈 lucro'} x{fmt(mlt)} por {seg // 60}min")
        if "bonus" in p:
            usados = u["presentes_c"].get(item.value, 0)
            if usados < p["limite"]:
                u["b_amor"] = round(u["b_amor"] + p["bonus"], 2)
                extras.append(f"❤️ +{p['bonus']}% de amor permanente")
        u["presentes_c"][item.value] = u["presentes_c"].get(item.value, 0) + 1
        u["n_pres"] += 1
        logar(u, f"{p['emoji']} Deu {p['nome']} para {m['name']} (-R$ {fmt(preco)}, +{fmt(ganho)} pts)")
        processar_niveis(u)
        aviso = coletar(u)
        store.save()
    await responder(
        interaction,
        "presentes",
        content=(
            f"{p['emoji']} **{m['name']}** adorou o(a) {p['nome']}! Você gastou R$ {fmt(preco)}: "
            f"**+{fmt(ganho)} pts** de amor" + ("".join(f"\n{x}" for x in extras)) + (f"\n{aviso}" if aviso else "")
        ),
    )


presentes.autocomplete("nome")(remover_auto)


# ---- /casamento -------------------------------------------------------------
@bot.tree.command(name="casamento", description="Cerimônia de casamento desbloqueável (requisitos e recompensas)")
@app_commands.describe(nome="Qual Main (padrão: a de maior nível)")
async def casamento(interaction: discord.Interaction, nome: str | None = None):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        marcar(u, interaction)
        if u.get("casada"):
            store.save()
            await interaction.response.send_message(
                f"💍 Você já é casado(a) com **{u['casada']}**! O casamento só pode ser feito uma vez.",
                ephemeral=True,
            )
            return
        if nome:
            m = next((x for x in u["waifus"] if x["name"] == nome), None)
        else:
            m = max(u["waifus"], key=lambda x: x["love"])
        if m is None:
            await interaction.response.send_message("Você não tem essa Main.", ephemeral=True)
            return
        reqs = req_casamento(u, m)
        store.save()
    pronto = all(ok for _, ok in reqs)
    e = discord.Embed(
        title=f"💒 Casamento com {m['name']}",
        description="\n".join(f"{'✅' if ok else '❌'} {t}" for t, ok in reqs),
        color=ROSA,
    )
    e.add_field(
        name="🎁 Recompensas",
        value=(
            f"💰 +{CASAMENTO_BONUS}% dinheiro e ❤️ +{CASAMENTO_BONUS}% amor permanentes\n"
            f"💠 +{CASAMENTO_FRAGMENTOS} fragmentos\n💍 Moldura exclusiva *Aliança*\n🏷️ Título *Casado(a) com {m['name']}*"
        ),
        inline=False,
    )
    e.set_thumbnail(url=m["image"])
    nome_main = m["name"]

    async def realizar(inter: discord.Interaction):
        async with store.lock:
            u2 = store.user(inter.user.id)
            m2 = next((x for x in u2["waifus"] if x["name"] == nome_main), None) if u2 else None
            if u2 is None or m2 is None or u2.get("casada") or not all(ok for _, ok in req_casamento(u2, m2)):
                await inter.response.edit_message(content="Algo mudou e você não cumpre mais os requisitos.", embed=None, view=None)
                return
            preco = custo_casamento(u2)
            u2["money"] = round(u2["money"] - preco, 2)
            u2["casada"] = nome_main
            u2["b_lucro"] += CASAMENTO_BONUS
            u2["b_amor"] += CASAMENTO_BONUS
            u2["fragmentos"] += CASAMENTO_FRAGMENTOS
            if "alianca" not in u2["molduras"]:
                u2["molduras"].append("alianca")
            logar(u2, f"💒 Casou com {nome_main} (-R$ {fmt(preco)})")
            processar_niveis(u2)
            store.save()
        fim = discord.Embed(
            title="💒 Vocês estão casados!",
            description=(
                f"**{inter.user.display_name}** e **{nome_main}** disseram \"sim\" 💍\n"
                f"Bônus permanentes de +{CASAMENTO_BONUS}% de dinheiro e amor, +{CASAMENTO_FRAGMENTOS} 💠 e a moldura *Aliança* "
                "(use `/molduras`)."
            ),
            color=ROSA,
        )
        fim.set_image(url=m["image"])
        await inter.response.edit_message(content=None, embed=fim, view=None)

    if not pronto:
        await interaction.response.send_message(embed=e, ephemeral=True)
        return
    await interaction.response.send_message(
        embed=e, view=ConfirmarView(interaction.user.id, realizar), ephemeral=True
    )


casamento.autocomplete("nome")(remover_auto)


# ---- /titulos ---------------------------------------------------------------
@bot.tree.command(name="titulos", description="Veja e equipe os títulos que você desbloqueou")
@app_commands.describe(equipar="Título para equipar (ou remover)")
async def titulos(interaction: discord.Interaction, equipar: str | None = None):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        marcar(u, interaction)
        todos = titulos_do(u)
        msg = None
        if equipar:
            if equipar == "-":
                u["titulo"] = None
                msg = "Título removido."
            elif equipar in todos:
                u["titulo"] = equipar
                msg = f"Título equipado: **{todos[equipar]}**"
            else:
                msg = "Você não tem esse título."
        aviso = coletar(u)
        store.save()
    atual = todos.get(u.get("titulo"), "nenhum")
    linhas = [f"{'➡️' if k == u.get('titulo') else '🏷️'} {v}" for k, v in todos.items()] or ["Nenhum ainda."]
    total_conq = len(CONQUISTAS)
    e = discord.Embed(
        title=f"🏷️ Títulos ({len(todos)})",
        description="\n".join(linhas)[:3900],
        color=ROSA,
    )
    e.add_field(name="Equipado", value=atual, inline=False)
    e.set_footer(text=f"Títulos vêm de conquistas ({len(u['conq'])}/{total_conq}), casamento, álbum e renascimentos.")
    await responder(interaction, "titulos", content="\n".join(x for x in (msg, aviso) if x) or None, embed=e)


async def titulos_auto(interaction: discord.Interaction, atual: str):
    u = store.data.get(str(interaction.user.id))
    if not u:
        return []
    opcoes = [("(remover título)", "-")] + [(v, k) for k, v in titulos_do(u).items()]
    return [app_commands.Choice(name=n[:100], value=k) for n, k in opcoes if atual.lower() in n.lower()][:25]


titulos.autocomplete("equipar")(titulos_auto)


# ---- /prestigio -------------------------------------------------------------
@bot.tree.command(name="prestigio", description="Árvore de habilidades exclusiva para quem já renasceu")
@app_commands.describe(habilidade="Habilidade para melhorar (vazio = ver a árvore)")
@app_commands.choices(
    habilidade=[app_commands.Choice(name=f"{v[0]} {v[1]}", value=k) for k, v in PRESTIGIO.items()]
)
async def prestigio(interaction: discord.Interaction, habilidade: app_commands.Choice[str] | None = None):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        marcar(u, interaction)
        if u["renasc"] < 1:
            store.save()
            await interaction.response.send_message(
                "🌳 O prestígio é só para quem já renasceu. Use `/renascer` (precisa de "
                f"R$ {fmt(RENASCER_MIN)}/s) — cada renascimento rende **1 ponto**.",
                ephemeral=True,
            )
            return
        msg = None
        if habilidade:
            k = habilidade.value
            lvl = pl(u, k)
            _, nome_h, _, maxl, _ = PRESTIGIO[k]
            c = custo_prest(k, lvl)
            if lvl >= maxl:
                msg = f"**{nome_h}** já está no nível máximo."
            elif prest_pts(u) < c:
                msg = f"Você precisa de {c} ponto(s) de prestígio (tem {prest_pts(u)})."
            else:
                u["prest"][k] = lvl + 1
                u["prest_gasto"] += c
                logar(u, f"🌳 Prestígio: {nome_h} nível {lvl + 1}")
                msg = f"✅ **{nome_h}** subiu para o nível {lvl + 1}/{maxl}!"
                processar_niveis(u)
        aviso = coletar(u)
        store.save()
    e = discord.Embed(
        title="🌳 Árvore de prestígio",
        description=f"Pontos disponíveis: **{prest_pts(u)}** (1 por renascimento — você renasceu {u['renasc']}x)",
        color=ROSA,
    )
    for k, (em, nome_h, desc, maxl, _) in PRESTIGIO.items():
        lvl = pl(u, k)
        prox = f"custo do próximo: {custo_prest(k, lvl)}" if lvl < maxl else "MAX"
        e.add_field(
            name=f"{em} {nome_h} — {lvl}/{maxl}",
            value=f"{desc} por nível • {prox}",
            inline=False,
        )
    await responder(interaction, "prestigio", content="\n".join(x for x in (msg, aviso) if x) or None, embed=e)


# ---- /duelo -----------------------------------------------------------------
class DueloView(discord.ui.View):
    def __init__(self, a: int, b: int, aposta: float):
        super().__init__(timeout=90)
        self.a, self.b, self.aposta = a, b, aposta

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.b:
            await interaction.response.send_message("Só quem foi desafiado pode responder.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Aceitar", style=discord.ButtonStyle.danger)
    async def aceitar(self, interaction: discord.Interaction, _):
        async with store.lock:
            ua, ub = store.user(self.a), store.user(self.b)
            erro = None
            if not ua or not ub or not ua["waifus"] or not ub["waifus"]:
                erro = "Algum dos dois não tem mais Mains. Duelo cancelado."
            elif ua["money"] < self.aposta or ub["money"] < self.aposta:
                erro = "Alguém não tem mais dinheiro para a aposta. Duelo cancelado."
            if erro:
                self.stop()
                await interaction.response.edit_message(content=erro, embed=None, view=None)
                return
            pa, pb = poder(ua), poder(ub)
            sa, sb = random.uniform(0, 40), random.uniform(0, 40)
            if pa + sa >= pb + sb:
                venc, perd, vid, pid = ua, ub, self.a, self.b
            else:
                venc, perd, vid, pid = ub, ua, self.b, self.a
            if self.aposta > 0:
                perd["money"] = round(perd["money"] - self.aposta, 2)
                add_money(venc, self.aposta)
            venc["vitorias"] += 1
            perd["derrotas"] += 1
            venc["fragmentos"] += DUELO_FRAGMENTOS
            logar(venc, f"⚔️ Venceu um duelo contra <@{pid}> (+R$ {fmt(self.aposta)})")
            logar(perd, f"⚔️ Perdeu um duelo para <@{vid}> (-R$ {fmt(self.aposta)})")
            processar_niveis(venc)
            store.save()
        self.stop()
        e = discord.Embed(title="⚔️ Resultado do duelo", color=ROSA)
        e.add_field(name="Desafiante", value=f"<@{self.a}>\nPoder {fmt(pa, 1)} + sorte {fmt(sa, 1)} = **{fmt(pa + sa, 1)}**", inline=True)
        e.add_field(name="Desafiado", value=f"<@{self.b}>\nPoder {fmt(pb, 1)} + sorte {fmt(sb, 1)} = **{fmt(pb + sb, 1)}**", inline=True)
        e.add_field(
            name="🏆 Vencedor",
            value=f"<@{vid}> levou **R$ {fmt(self.aposta)}** e +{DUELO_FRAGMENTOS} 💠",
            inline=False,
        )
        await interaction.response.edit_message(content=None, embed=e, view=None)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.secondary)
    async def recusar(self, interaction: discord.Interaction, _):
        self.stop()
        await interaction.response.edit_message(content=f"<@{self.b}> recusou o duelo.", embed=None, view=None)


@bot.tree.command(name="duelo", description="Desafia outro jogador para um duelo (com aposta opcional)")
@app_commands.describe(adversario="Quem desafiar", aposta="Dinheiro apostado (0 = só pela honra)")
async def duelo(interaction: discord.Interaction, adversario: discord.Member, aposta: app_commands.Range[int, 0, 10**15] = 0):
    if adversario.bot or adversario.id == interaction.user.id:
        await interaction.response.send_message("Escolha outro jogador.", ephemeral=True)
        return
    async with store.lock:
        ua, ub = store.user(interaction.user.id), store.user(adversario.id)
        if ua is None or not ua["waifus"]:
            await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
            return
        if ub is None or not ub["waifus"]:
            await interaction.response.send_message(f"{adversario.display_name} ainda não joga.", ephemeral=True)
            return
        agora = time.time()
        falta = ua["t_duelo"] + DUELO_ESPERA - agora
        if falta > 0:
            await interaction.response.send_message(f"Você precisa descansar. Volte em {_tempo(falta)} ⏰", ephemeral=True)
            return
        if ua["money"] < aposta or ub["money"] < aposta:
            await interaction.response.send_message(
                "Os dois precisam ter pelo menos o valor da aposta em dinheiro.", ephemeral=True
            )
            return
        ua["t_duelo"] = agora
        marcar(ua, interaction)
        store.save()
    e = discord.Embed(
        title="⚔️ Desafio de duelo!",
        description=(
            f"{interaction.user.mention} desafiou {adversario.mention}"
            + (f" valendo **R$ {fmt(aposta)}**" if aposta else " (sem aposta)")
            + "\n\n**Regras:** poder = nível da Main mais alta ×10 + classe ×15 + log do lucro ×10 + renascimentos ×5, "
            f"mais sorte (0–40). Quem tiver mais leva a aposta e {DUELO_FRAGMENTOS} 💠."
        ),
        color=ROSA,
    )
    await interaction.response.send_message(
        content=adversario.mention, embed=e, view=DueloView(interaction.user.id, adversario.id, float(aposta))
    )


# ---- /sorteio ---------------------------------------------------------------
ANILIST_RANDOM = """
query ($p: Int) {
  Page(page: $p, perPage: 1) {
    characters(sort: FAVOURITES_DESC) {
      name { full }
      image { large }
      media(perPage: 1, sort: POPULARITY_DESC) { nodes { title { romaji } } }
    }
  }
}
"""


async def personagem_aleatoria(session: aiohttp.ClientSession) -> dict | None:
    async with session.post(
        "https://graphql.anilist.co",
        json={"query": ANILIST_RANDOM, "variables": {"p": random.randint(1, 400)}},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as r:
        r.raise_for_status()
        data = await r.json()
    cs = data["data"]["Page"]["characters"]
    if not cs:
        return None
    c = cs[0]
    nodes = c["media"]["nodes"]
    if not c["image"]["large"]:
        return None
    return {
        "name": c["name"]["full"],
        "image": c["image"]["large"],
        "anime": nodes[0]["title"]["romaji"] if nodes else None,
        "tipo": "anime",
    }


@bot.tree.command(name="sorteio", description="Gasta dinheiro do jogo num sorteio de personagem ou recompensa")
async def sorteio(interaction: discord.Interaction):
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        preco = custo_sorteio(u)
        if u["money"] < preco:
            await interaction.response.send_message(
                f"Um sorteio custa R$ {fmt(preco)} e você tem R$ {fmt(u['money'])}.", ephemeral=True
            )
            return
    await interaction.response.defer()
    roll = random.random()
    char = None
    if roll < 0.55:  # personagem
        try:
            char = await personagem_aleatoria(bot.session)
        except Exception as ex:
            print(f"[sorteio] anilist falhou: {ex}")
        if char is None:
            roll = 0.60  # sem rede: cai numa recompensa
    async with store.lock:
        u = store.user(interaction.user.id)
        if u is None or u["money"] < preco:
            await interaction.followup.send("Seu saldo mudou e não dá mais para o sorteio.", ephemeral=True)
            return
        u["money"] = round(u["money"] - preco, 2)
        marcar(u, interaction)
        e = discord.Embed(title="🎟️ Sorteio", color=ROSA)
        if char is not None:
            nova, frag = obter_personagem(u, char)
            r_nome, r_emoji, r_cor, _ = RARIDADES[raridade_idx(char["name"])]
            e.color = discord.Colour(r_cor)
            e.title = f"🎟️ Sorteio — {r_emoji} {r_nome}"
            e.description = f"**{char['name']}**" + (f"\n📺 {char['anime']}" if char["anime"] else "")
            e.set_image(url=char["image"])
            if nova:
                e.add_field(name="Nova na coleção!", value="Use `/equipar` para colocá-la num slot.", inline=False)
                logar(u, f"🎟️ Sorteio: {r_emoji} {char['name']} (nova)")
            else:
                e.add_field(name="Repetida!", value=f"Virou **+{frag} 💠** fragmentos.", inline=False)
                logar(u, f"🎟️ Sorteio: {char['name']} repetida (+{frag} fragmentos)")
        elif roll < 0.75:
            g = lucro_efetivo(u) * random.randint(1200, 3600)
            g = max(g, preco * 0.5)
            add_money(u, g)
            e.description = f"💰 Você ganhou **R$ {fmt(g)}**!"
            logar(u, f"🎟️ Sorteio: +R$ {fmt(g)}")
        elif roll < 0.85:
            m = random.choice(u["waifus"])
            n, _, prox = nivel(m["love"])
            g = (prox - limiar(n)) * random.uniform(0.10, 0.20) if prox else 0.0
            m["love"] += g
            e.description = f"💘 **{m['name']}** gostou da sorte! **+{fmt(g)} pts** de amor"
            logar(u, f"🎟️ Sorteio: +{fmt(g)} pts de amor para {m['name']}")
        elif roll < 0.93:
            f = random.randint(3, 15)
            u["fragmentos"] += f
            e.description = f"💠 Você ganhou **{f} fragmentos**!"
            logar(u, f"🎟️ Sorteio: +{f} fragmentos")
        elif roll < 0.98:
            tipo = random.choice(["lucro", "amor"])
            _buff(u, tipo, 2.0, 600)
            e.description = f"✨ **{'Lucro' if tipo == 'lucro' else 'Amor'} x2** por 10 minutos!"
            logar(u, f"🎟️ Sorteio: {tipo} x2 por 10min")
        else:
            g = max(1000.0, lucro_efetivo(u) * 20_000)
            add_money(u, g)
            e.title = "🎟️ Sorteio — 🌟 JACKPOT!"
            e.description = f"🎰 **R$ {fmt(g)}**!!!"
            logar(u, f"🎟️ Sorteio JACKPOT: +R$ {fmt(g)}")
        processar_niveis(u)
        aviso = coletar(u)
        store.save()
    e.set_footer(text=f"Custo: R$ {fmt(preco)}")
    await interaction.followup.send(content=aviso, embed=e)


# ---- /colecao, /equipar, /molduras -------------------------------------------


@bot.tree.command(name="colecao", description="Mostra todas as personagens que você já obteve")
@app_commands.describe(pagina="Página da lista (padrão 1)")
async def colecao(interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 999] = 1):
    async with store.lock:
        u = store.user(interaction.user.id)
        if u is None or not u["colecao"]:
            await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
            return
        marcar(u, interaction)
        aviso = coletar(u)
        store.save()
    equipadas = {m["name"]: m for m in u["waifus"]}
    itens = sorted(u["colecao"].items(), key=lambda kv: (-raridade_idx(kv[0]), kv[0].lower()))
    total_pag = max(1, math.ceil(len(itens) / POR_PAGINA))
    pagina = min(pagina, total_pag)
    linhas = []
    for nome, ent in itens[(pagina - 1) * POR_PAGINA : pagina * POR_PAGINA]:
        r_nome, r_emoji, _, _ = RARIDADES[raridade_idx(nome)]
        if nome in equipadas:
            estado = f"⭐ equipada (Nv {nivel(equipadas[nome]['love'])[0]})"
        else:
            estado = f"📦 guardada (Nv {nivel(ent.get('love', 0.0))[0]})"
        if u.get("casada") == nome:
            estado += " 💍"
        extra = f" ×{ent['qtd']}" if ent.get("qtd", 1) > 1 else ""
        linhas.append(f"{r_emoji} **{nome}**{extra} — {estado}")
    cont = {r[0]: 0 for r in RARIDADES}
    for nome in u["colecao"]:
        cont[RARIDADES[raridade_idx(nome)][0]] += 1
    mold, cor = moldura_info(u)
    e = discord.Embed(
        title=f"{mold} 📚 Coleção ({len(u['colecao'])})".strip(),
        description="\n".join(linhas),
        color=cor,
    )
    e.add_field(
        name="📖 Álbum",
        value=f"{barra(len(u['colecao']), 0, ALBUM_META)} — **{album_pct(u):.1f}%** completo",
        inline=False,
    )
    e.add_field(
        name="✨ Raridades",
        value=" • ".join(f"{r[1]} {cont[r[0]]}" for r in RARIDADES) + f"\n💠 Fragmentos: **{u['fragmentos']}**",
        inline=False,
    )
    e.set_footer(text=f"Página {pagina}/{total_pag} • /equipar para colocar num slot • /molduras para gastar fragmentos")
    await responder(interaction, "colecao", content=aviso, embed=e)


async def colecao_auto(interaction: discord.Interaction, atual: str):
    u = store.data.get(str(interaction.user.id))
    if not u:
        return []
    equipadas = {m["name"] for m in u["waifus"]}
    return [
        app_commands.Choice(name=n[:100], value=n[:100])
        for n in u["colecao"]
        if n not in equipadas and atual.lower() in n.lower()
    ][:25]


@bot.tree.command(name="equipar", description="Coloca uma personagem da coleção num slot de Main (com o progresso dela)")
@app_commands.describe(nome="Personagem da coleção", trocar="Main para tirar do slot (se estiver cheio)")
async def equipar(interaction: discord.Interaction, nome: str, trocar: str | None = None):
    async with store.lock:
        u = store.user(interaction.user.id)
        if u is None or not u["colecao"]:
            await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
            return
        marcar(u, interaction)
        trocou = False
        if trocar:
            m = next((x for x in u["waifus"] if x["name"] == trocar), None)
            if m is None:
                await interaction.response.send_message("A Main a trocar não está equipada.", ephemeral=True)
                return
            if len(u["waifus"]) >= slots_total(u):  # só troca se o slot estiver cheio
                guardar_main(u, m)
                u["waifus"].remove(m)
                trocou = True
        erro = equipar_main(u, nome)
        if erro:
            store.save()
            await interaction.response.send_message(erro, ephemeral=True)
            return
        logar(u, f"⭐ Equipou {nome}" + (f" no lugar de {trocar}" if trocou else ""))
        aviso = coletar(u)
        store.save()
    await responder(
        interaction,
        "equipar",
        content=f"⭐ **{nome}** voltou para um slot de Main com o progresso guardado ({len(u['waifus'])}/{slots_total(u)})."
        + (f" **{trocar}** foi para a coleção." if trocou else "")
        + (f"\n{aviso}" if aviso else ""),
    )


equipar.autocomplete("nome")(colecao_auto)
equipar.autocomplete("trocar")(remover_auto)


@bot.tree.command(name="molduras", description="Gaste fragmentos em molduras exclusivas e equipe a que quiser")
@app_commands.describe(item="Moldura para comprar/equipar (vazio = ver tudo)")
@app_commands.choices(
    item=[app_commands.Choice(name=f"{v[0]} {v[1]}"[:100], value=k) for k, v in MOLDURAS.items()]
    + [app_commands.Choice(name="Nenhuma (tirar moldura)", value="-")]
)
async def molduras(interaction: discord.Interaction, item: app_commands.Choice[str] | None = None):
    async with store.lock:
        u = store.user(interaction.user.id)
        if u is None or not u["colecao"]:
            await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
            return
        marcar(u, interaction)
        msg = None
        if item:
            k = item.value
            if k == "-":
                u["moldura"] = None
                msg = "Moldura removida."
            elif k in u["molduras"]:
                u["moldura"] = k
                msg = f"{MOLDURAS[k][0]} Moldura **{MOLDURAS[k][1]}** equipada!"
            elif MOLDURAS[k][2] is None:
                msg = "Essa moldura é exclusiva do casamento (`/casamento`)."
            elif u["fragmentos"] < MOLDURAS[k][2]:
                msg = f"Faltam {MOLDURAS[k][2] - u['fragmentos']} 💠 para essa moldura."
            else:
                u["fragmentos"] -= MOLDURAS[k][2]
                u["molduras"].append(k)
                u["moldura"] = k
                logar(u, f"🖼️ Comprou a moldura {MOLDURAS[k][1]}")
                msg = f"{MOLDURAS[k][0]} Você comprou e equipou **{MOLDURAS[k][1]}**!"
        aviso = coletar(u)
        store.save()
    mold, cor = moldura_info(u)
    linhas = []
    for k, (em, nome_m, custo_m, _) in MOLDURAS.items():
        if k in u["molduras"]:
            estado = "✅ equipada" if u.get("moldura") == k else "✅ sua"
        else:
            estado = "🔒 exclusiva" if custo_m is None else f"💠 {custo_m}"
        linhas.append(f"{em} **{nome_m}** — {estado}")
    e = discord.Embed(title="🖼️ Molduras", description="\n".join(linhas), color=cor)
    e.set_footer(text=f"Seus fragmentos: {u['fragmentos']} (repetidas e duelos rendem fragmentos)")
    await responder(interaction, "molduras", content="\n".join(x for x in (msg, aviso) if x) or None, embed=e)


# ---- /historico -------------------------------------------------------------
@bot.tree.command(name="historico", description="Mostra seus últimos eventos, compras e mudanças de nível")
async def historico(interaction: discord.Interaction):
    ini = await iniciar_comando(interaction)
    if ini is None:
        return
    u, aviso = ini
    ult = u["log"][-15:][::-1]
    texto = "\n".join(f"<t:{x['t']}:R> {x['m']}" for x in ult) or "Nada por aqui ainda."
    e = discord.Embed(title="📜 Histórico", description=texto[:4000], color=ROSA)
    e.set_footer(text=f"Mostrando {len(ult)} de {len(u['log'])} registros guardados")
    await responder(interaction, "historico", content=aviso, embed=e)


# ---- /mercado ---------------------------------------------------------------
mercado = app_commands.Group(name="mercado", description="Compre e venda itens e cosméticos com outros jogadores")
bot.tree.add_command(mercado)


def _desc_anuncio(a: dict) -> str:
    if a["tipo"] == "fragmentos":
        return f"💠 {a['qtd']} fragmentos"
    if a["tipo"] == "moldura":
        em, nome_m, _, _ = MOLDURAS[a["item"]]
        return f"{em} Moldura {nome_m}"
    r = RARIDADES[raridade_idx(a["item"])]
    return f"{r[1]} {a['item']} ({r[0]})"


@mercado.command(name="ver", description="Lista os anúncios do mercado")
async def mercado_ver(interaction: discord.Interaction):
    anuncios = store.meta["mercado"][-20:][::-1]
    linhas = [
        f"`#{a['id']}` {_desc_anuncio(a)} — **R$ {fmt(a['preco'])}** • <@{a['vendedor']}>" for a in anuncios
    ] or ["Nenhum anúncio no momento."]
    e = discord.Embed(title="🏪 Mercado", description="\n".join(linhas), color=ROSA)
    e.set_footer(text=f"Taxa de venda: {int(MERCADO_TAXA * 100)}% • /mercado comprar id:...")
    await interaction.response.send_message(embed=e)


@mercado.command(name="vender", description="Anuncia um item ou cosmético")
@app_commands.describe(
    tipo="O que vender",
    preco="Preço em R$",
    item="Moldura ou personagem (não precisa para fragmentos)",
    quantidade="Quantidade (só para fragmentos)",
)
@app_commands.choices(
    tipo=[
        app_commands.Choice(name="💠 Fragmentos", value="fragmentos"),
        app_commands.Choice(name="🖼️ Moldura", value="moldura"),
        app_commands.Choice(name="📚 Personagem da coleção", value="personagem"),
    ]
)
async def mercado_vender(
    interaction: discord.Interaction,
    tipo: app_commands.Choice[str],
    preco: app_commands.Range[int, 1, 10**15],
    item: str | None = None,
    quantidade: app_commands.Range[int, 1, 100000] = 1,
):
    async with store.lock:
        u = store.user(interaction.user.id)
        if u is None or not u["colecao"]:
            await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
            return
        if sum(1 for a in store.meta["mercado"] if a["vendedor"] == interaction.user.id) >= MERCADO_MAX_ANUNCIOS:
            await interaction.response.send_message(
                f"Você já tem {MERCADO_MAX_ANUNCIOS} anúncios ativos. Cancele algum antes.", ephemeral=True
            )
            return
        marcar(u, interaction)
        anuncio = {
            "id": store.meta["mercado_prox"],
            "vendedor": interaction.user.id,
            "tipo": tipo.value,
            "item": None,
            "qtd": 1,
            "preco": preco,
            "t": int(time.time()),
        }
        if tipo.value == "fragmentos":
            if u["fragmentos"] < quantidade:
                await interaction.response.send_message(f"Você só tem {u['fragmentos']} 💠.", ephemeral=True)
                return
            u["fragmentos"] -= quantidade
            anuncio["qtd"] = quantidade
        elif tipo.value == "moldura":
            if item not in u["molduras"] or item == "alianca":
                await interaction.response.send_message("Você não tem essa moldura (ou ela não é negociável).", ephemeral=True)
                return
            u["molduras"].remove(item)
            if u.get("moldura") == item:
                u["moldura"] = None
            anuncio["item"] = item
        else:
            ent = u["colecao"].get(item or "")
            if ent is None:
                await interaction.response.send_message("Você não tem essa personagem na coleção.", ephemeral=True)
                return
            if any(m["name"] == item for m in u["waifus"]):
                await interaction.response.send_message("Tire ela do slot primeiro (`/remover`).", ephemeral=True)
                return
            if u.get("casada") == item:
                await interaction.response.send_message("Você não vende a pessoa com quem casou 💍", ephemeral=True)
                return
            anuncio["item"] = item
            anuncio["ent"] = ent
            del u["colecao"][item]
        store.meta["mercado_prox"] += 1
        store.meta["mercado"].append(anuncio)
        logar(u, f"🏪 Anunciou {_desc_anuncio(anuncio)} por R$ {fmt(preco)}")
        store.save()
    await interaction.response.send_message(
        f"🏪 Anúncio **#{anuncio['id']}** criado: {_desc_anuncio(anuncio)} por **R$ {fmt(preco)}**."
    )


async def mercado_item_auto(interaction: discord.Interaction, atual: str):
    u = store.data.get(str(interaction.user.id))
    if not u:
        return []
    tipo = getattr(interaction.namespace, "tipo", None)
    if tipo == "moldura":
        opcoes = [(f"{MOLDURAS[k][0]} {MOLDURAS[k][1]}", k) for k in u["molduras"] if k != "alianca"]
    elif tipo == "personagem":
        equipadas = {m["name"] for m in u["waifus"]}
        opcoes = [(n, n) for n in u["colecao"] if n not in equipadas and u.get("casada") != n]
    else:
        return []
    return [app_commands.Choice(name=n[:100], value=v[:100]) for n, v in opcoes if atual.lower() in n.lower()][:25]


mercado_vender.autocomplete("item")(mercado_item_auto)


@mercado.command(name="comprar", description="Compra um anúncio pelo número")
@app_commands.describe(id="Número do anúncio")
async def mercado_comprar(interaction: discord.Interaction, id: int):
    async with store.lock:
        a = next((x for x in store.meta["mercado"] if x["id"] == id), None)
        if a is None:
            await interaction.response.send_message("Esse anúncio não existe mais.", ephemeral=True)
            return
        u = store.user(interaction.user.id)
        if u is None or not u["colecao"]:
            await interaction.response.send_message(NAO_COMECOU, ephemeral=True)
            return
        if a["vendedor"] == interaction.user.id:
            await interaction.response.send_message("Esse anúncio é seu (use `/mercado cancelar`).", ephemeral=True)
            return
        if u["money"] < a["preco"]:
            await interaction.response.send_message(
                f"Custa R$ {fmt(a['preco'])} e você tem R$ {fmt(u['money'])}.", ephemeral=True
            )
            return
        if a["tipo"] == "moldura" and a["item"] in u["molduras"]:
            await interaction.response.send_message("Você já tem essa moldura.", ephemeral=True)
            return
        vend = store.user(a["vendedor"])
        u["money"] = round(u["money"] - a["preco"], 2)
        if vend is not None:
            add_money(vend, a["preco"] * (1 - MERCADO_TAXA))
            logar(vend, f"🏪 Vendeu {_desc_anuncio(a)} por R$ {fmt(a['preco'] * (1 - MERCADO_TAXA))} (já sem taxa)")
        extra = ""
        if a["tipo"] == "fragmentos":
            u["fragmentos"] += a["qtd"]
        elif a["tipo"] == "moldura":
            u["molduras"].append(a["item"])
        else:
            ent = a["ent"]
            nova, frag = obter_personagem(
                u, {"name": a["item"], "image": ent["image"], "anime": ent.get("anime"), "tipo": ent.get("tipo", "anime")}
            )
            extra = "" if nova else f" (você já tinha: virou +{frag} 💠)"
        store.meta["mercado"].remove(a)
        marcar(u, interaction)
        logar(u, f"🏪 Comprou {_desc_anuncio(a)} por R$ {fmt(a['preco'])}")
        processar_niveis(u)
        store.save()
    await interaction.response.send_message(f"🏪 Você comprou {_desc_anuncio(a)} por **R$ {fmt(a['preco'])}**!{extra}")


@mercado.command(name="cancelar", description="Cancela um anúncio seu e recebe o item de volta")
@app_commands.describe(id="Número do anúncio")
async def mercado_cancelar(interaction: discord.Interaction, id: int):
    async with store.lock:
        a = next((x for x in store.meta["mercado"] if x["id"] == id and x["vendedor"] == interaction.user.id), None)
        u = store.user(interaction.user.id)
        if a is None or u is None:
            await interaction.response.send_message("Não achei esse anúncio seu.", ephemeral=True)
            return
        if a["tipo"] == "fragmentos":
            u["fragmentos"] += a["qtd"]
        elif a["tipo"] == "moldura":
            u["molduras"].append(a["item"])
        else:
            u["colecao"][a["item"]] = a["ent"]
        store.meta["mercado"].remove(a)
        logar(u, f"🏪 Cancelou o anúncio #{id}")
        store.save()
    await interaction.response.send_message(f"Anúncio **#{id}** cancelado e item devolvido.", ephemeral=True)


# ---- /codigos ---------------------------------------------------------------
codigos = app_commands.Group(name="codigos", description="Códigos promocionais")
bot.tree.add_command(codigos)


def _recompensa_txt(tipo: str, valor: float) -> str:
    return {
        "dinheiro": f"💰 R$ {fmt(valor)}",
        "fragmentos": f"💠 {fmt(valor)} fragmentos",
        "amor": f"❤️ {fmt(valor)} pts de amor para cada Main",
    }[tipo]


@codigos.command(name="resgatar", description="Resgata um código promocional")
@app_commands.describe(codigo="O código")
async def codigos_resgatar(interaction: discord.Interaction, codigo: str):
    chave = codigo.strip().upper()
    async with store.lock:
        u = await jogador_ativo(interaction)
        if u is None:
            return
        c = store.meta["codigos"].get(chave)
        agora = time.time()
        if c is None:
            await interaction.response.send_message("Código inválido.", ephemeral=True)
            return
        if c["ate"] and agora > c["ate"]:
            await interaction.response.send_message("Esse código expirou.", ephemeral=True)
            return
        if len(c["usados"]) >= c["usos"]:
            await interaction.response.send_message("Esse código já atingiu o limite de usos.", ephemeral=True)
            return
        if interaction.user.id in c["usados"]:
            await interaction.response.send_message("Você já resgatou esse código.", ephemeral=True)
            return
        c["usados"].append(interaction.user.id)
        if c["tipo"] == "dinheiro":
            add_money(u, c["valor"])
        elif c["tipo"] == "fragmentos":
            u["fragmentos"] += int(c["valor"])
        else:
            for m in u["waifus"]:
                m["love"] += c["valor"]
        marcar(u, interaction)
        logar(u, f"🎫 Código {chave}: {_recompensa_txt(c['tipo'], c['valor'])}")
        processar_niveis(u)
        aviso = coletar(u)
        store.save()
    await interaction.response.send_message(
        f"🎫 Código **{chave}** resgatado! {_recompensa_txt(c['tipo'], c['valor'])}" + (f"\n{aviso}" if aviso else "")
    )


@codigos.command(name="criar", description="(Admin) Cria um código promocional")
@app_commands.describe(
    codigo="Texto do código",
    tipo="Tipo de recompensa",
    valor="Quantidade da recompensa",
    horas="Validade em horas (0 = sem validade)",
    usos="Limite de usos no total",
)
@app_commands.choices(
    tipo=[
        app_commands.Choice(name="💰 Dinheiro", value="dinheiro"),
        app_commands.Choice(name="💠 Fragmentos", value="fragmentos"),
        app_commands.Choice(name="❤️ Amor (para cada Main)", value="amor"),
    ]
)
async def codigos_criar(
    interaction: discord.Interaction,
    codigo: str,
    tipo: app_commands.Choice[str],
    valor: app_commands.Range[float, 1],
    horas: app_commands.Range[int, 0, 24 * 365] = 24,
    usos: app_commands.Range[int, 1, 100000] = 100,
):
    if not await so_admin(interaction):
        return
    chave = codigo.strip().upper()
    async with store.lock:
        store.meta["codigos"][chave] = {
            "tipo": tipo.value,
            "valor": float(valor),
            "ate": time.time() + horas * 3600 if horas else 0,
            "usos": usos,
            "usados": [],
        }
        store.save()
    await interaction.response.send_message(
        f"🎫 Código **{chave}** criado: {_recompensa_txt(tipo.value, valor)} • "
        f"{usos} usos • {'sem validade' if not horas else f'válido por {horas}h'}",
        ephemeral=True,
    )


@codigos.command(name="listar", description="(Admin) Lista os códigos ativos")
async def codigos_listar(interaction: discord.Interaction):
    if not await so_admin(interaction):
        return
    agora = time.time()
    linhas = []
    for k, c in store.meta["codigos"].items():
        val = "sem validade" if not c["ate"] else (f"expira <t:{int(c['ate'])}:R>" if c["ate"] > agora else "expirado")
        linhas.append(f"`{k}` — {_recompensa_txt(c['tipo'], c['valor'])} • {len(c['usados'])}/{c['usos']} usos • {val}")
    await interaction.response.send_message("\n".join(linhas) or "Nenhum código.", ephemeral=True)


@codigos.command(name="apagar", description="(Admin) Apaga um código")
@app_commands.describe(codigo="O código")
async def codigos_apagar(interaction: discord.Interaction, codigo: str):
    if not await so_admin(interaction):
        return
    async with store.lock:
        existia = store.meta["codigos"].pop(codigo.strip().upper(), None) is not None
        store.save()
    await interaction.response.send_message("Código apagado." if existia else "Não achei esse código.", ephemeral=True)


# ---- /help ------------------------------------------------------------------
AJUDA = [
    (
        "🚀 Começar",
        "`/waifu nome` — busca uma personagem (anime, mangá, visual novel ou jogo) e escolhe como Main\n"
        "`/perfil` — dinheiro, lucro, classe, Mains, bônus e estatísticas\n"
        "`/casal` — cartão de casal de uma Main (nível, afinidade, imagem)\n"
        "`/diario` — recompensa diária com sequência (streak)\n"
        "`/resetar` — apaga tudo e recomeça",
    ),
    (
        "💰 Dinheiro e progresso",
        "`/trabalhar` — bico rápido (a cada 5 min)\n"
        "`/loja` e `/comprar` — upgrades de lucro e de relacionamento\n"
        "`/classe` — Bronze até Divino e seu progresso\n"
        "`/conquistas` — conquistas com recompensas\n"
        "`/renascer` — zera dinheiro/upgrades por +10% permanente e 1 ponto de prestígio\n"
        "`/prestigio` — árvore de habilidades de quem já renasceu",
    ),
    (
        "💞 Relacionamento",
        "`/encontro` — leva uma Main para sair (a cada 2h)\n"
        "`/presentear` — gasta dinheiro livre para dar amor\n"
        "`/presentes` — catálogo de presentes com efeitos diferentes\n"
        "`/casamento` — cerimônia com requisitos e recompensas\n"
        "`/remover` — tira uma Main do slot (o progresso fica guardado)",
    ),
    (
        "📚 Coleção e cosméticos",
        "`/colecao` — todas as personagens, raridades e álbum\n"
        "`/equipar` — coloca uma personagem da coleção num slot\n"
        "`/sorteio` — sorteio de personagem ou recompensa com dinheiro do jogo\n"
        "`/molduras` — gasta fragmentos 💠 em molduras\n"
        "`/titulos` — equipa títulos de conquistas, casamento, álbum e renascimentos",
    ),
    (
        "⚔️ Social",
        "`/duelo` — desafia outro jogador (aposta opcional)\n"
        "`/mercado ver|vender|comprar|cancelar` — negocia fragmentos, molduras e personagens\n"
        "`/ranking` — top 10 por classe, dinheiro, lucro, tempo de jogo, encontros e mais\n"
        "`/codigos resgatar` — usa um código promocional",
    ),
    (
        "📜 Outros",
        "`/historico` — últimos eventos, compras e mudanças de nível\n"
        "`/help` — esta lista\n"
        "Admins: `/status`, `/codigos criar|listar|apagar`",
    ),
    (
        "ℹ️ Como funciona",
        "• Lucro base: 1 real/s + upgrades. O amor é dividido entre as Mains equipadas.\n"
        "• Cada Main sobe de nível (1–25): dá pontos de classe, slots e bônus %.\n"
        "• Lucro muito alto reduz um pouco o ganho de amor.\n"
        "• Ao usar comandos podem rolar eventos aleatórios, bons ou ruins.\n"
        "• Repetir o mesmo comando edita a mensagem anterior.",
    ),
]


@bot.tree.command(name="help", description="Mostra todos os comandos e funcionalidades do bot")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(
        title="💖 Simulador de namoro — Ajuda",
        description="Junte dinheiro, conquiste suas Mains e colecione personagens!",
        color=ROSA,
    )
    for titulo, texto in AJUDA:
        e.add_field(name=titulo, value=texto, inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


# ----------------------------------------------------------------------------
# Comandos ocultos com prefixo $ (não aparecem na barra de Slash commands)
#   $change -> altera as estatísticas de qualquer player do servidor atual
#   $help   -> explica cada funcionalidade do $change
# Só respondem ao CHANGE_USER_ID (os outros são ignorados em silêncio).
# Precisa do "Message Content Intent" ligado no Developer Portal
# (Bot -> Privileged Gateway Intents).
# ----------------------------------------------------------------------------


class Campo(NamedTuple):
    nome: str  # como se digita no comando
    rotulo: str  # como aparece nas respostas
    chave: str  # campo no save do player
    tipo: str  # "int" ou "float"
    escala: float  # valor digitado * escala = valor salvo (ex.: horas -> segundos)
    minimo: float
    maximo: float
    apelidos: tuple
    desc: str
    pre: str = ""
    suf: str = ""


CAMPOS = [
    Campo("dinheiro", "💰 Dinheiro", "money", "float", 1, 0, MAX_FLOAT, ("money", "grana"), "dinheiro atual", "R$ "),
    Campo("total", "🏦 Dinheiro acumulado", "tot_money", "float", 1, 0, MAX_FLOAT, ("acumulado",), "total ganho na vida da conta", "R$ "),
    Campo("fragmentos", "💠 Fragmentos", "fragmentos", "int", 1, 0, MAX_INT, ("frag",), "fragmentos de moldura"),
    Campo("pontos", "🏆 Pontos de classe", "cp", "int", 1, 0, MAX_INT, ("cp",), "pontos de classe (definem Bronze...Divino)"),
    Campo("bonuslucro", "📈 Bônus de dinheiro", "b_lucro", "float", 1, 0, MAX_FLOAT, ("blucro",), "% permanente de dinheiro", "", "%"),
    Campo("bonusamor", "💗 Bônus de amor", "b_amor", "float", 1, 0, MAX_FLOAT, ("bamor",), "% permanente de amor", "", "%"),
    Campo("renascimentos", "🔁 Renascimentos", "renasc", "int", 1, 0, MAX_INT, ("renasc",), "quantidade de renascimentos"),
    Campo("prestgasto", "🌳 Prestígio gasto", "prest_gasto", "int", 1, 0, MAX_INT, ("gasto",), "pontos de prestígio já gastos (livres = renascimentos − gastos)"),
    Campo("slots", "🎟️ Slots de Main", "slots", "int", 1, 1, MAX_SLOTS, (), f"slots de Main (1 a {MAX_SLOTS})"),
    Campo("streak", "🔥 Sequência do /diario", "streak", "int", 1, 0, MAX_INT, (), "sequência atual do /diario"),
    Campo("maxstreak", "📅 Maior sequência", "max_streak", "int", 1, 0, MAX_INT, (), "maior sequência do /diario"),
    Campo("encontros", "🍷 Encontros", "n_enc", "int", 1, 0, MAX_INT, ("enc",), "encontros feitos"),
    Campo("presentes", "🎁 Presentes dados", "n_pres", "int", 1, 0, MAX_INT, ("pres",), "presentes dados"),
    Campo("vitorias", "🏅 Vitórias em duelo", "vitorias", "int", 1, 0, MAX_INT, ("vit",), "vitórias em duelo"),
    Campo("derrotas", "💔 Derrotas em duelo", "derrotas", "int", 1, 0, MAX_INT, ("der",), "derrotas em duelo"),
    Campo("horas", "⏳ Tempo de jogo", "t_jogo", "float", 3600, 0, MAX_FLOAT, ("tempo",), "tempo de jogo, em horas", "", " h"),
]


def _norm(s: str) -> str:
    """Minúsculas, sem acentos, espaços, '-' e '_' (para comparar nomes)."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace(" ", "").replace("-", "").replace("_", "")


CAMPO_POR_NOME = {_norm(n): c for c in CAMPOS for n in (c.nome, *c.apelidos)}

# sufixos aceitos nos valores (os mais longos primeiro)
_SUFIXOS = (
    ("quint", 1e18), ("quad", 1e15), ("sext", 1e21), ("tri", 1e12), ("mil", 1e3),
    ("bi", 1e9), ("mi", 1e6), ("k", 1e3), ("m", 1e6), ("b", 1e9), ("t", 1e12),
)


def parse_valor(txt: str) -> tuple[str, float]:
    """'500' / '=500' define, '+500' soma, '-500' subtrai. Aceita 2,5bi, 10k, 1e9..."""
    t = txt.strip().lower().replace("_", "")
    modo = "set"
    if t and t[0] in "+-=":
        modo = {"+": "add", "-": "sub", "=": "set"}[t[0]]
        t = t[1:]
    fator = 1.0
    for suf, f in _SUFIXOS:
        if t.endswith(suf):
            t, fator = t[: -len(suf)], f
            break
    try:
        v = float(t.replace(",", ".")) * fator
    except ValueError:
        raise ValueError(f"Valor inválido: `{txt}`") from None
    if not math.isfinite(v):
        raise ValueError(f"Valor inválido: `{txt}`")
    return modo, v


def _aplicar(atual: float, modo: str, v: float, minimo: float, maximo: float, tipo: str):
    novo = v if modo == "set" else atual + v if modo == "add" else atual - v
    novo = min(maximo, max(minimo, novo))
    return int(round(novo)) if tipo == "int" else round(novo, 2)


def _txt_valor(c: Campo, v: float) -> str:
    return f"{c.pre}{fmt(v)}{c.suf}"


def _achar_main(u: dict, nome: str) -> tuple[str, dict]:
    """Acha uma Main (equipada ou guardada na coleção). Sem nome = a primeira equipada."""
    if not nome:
        if not u["waifus"]:
            raise ValueError("esse player não tem Main equipada (diga o nome de uma da coleção)")
        m = u["waifus"][0]
        return m["name"], m
    equipadas = {m["name"] for m in u["waifus"]}
    opcoes = [(m["name"], m) for m in u["waifus"]]
    opcoes += [(n, e) for n, e in u["colecao"].items() if n not in equipadas]
    alvo = _norm(nome)
    exatas = [o for o in opcoes if _norm(o[0]) == alvo]
    parecidas = exatas or [o for o in opcoes if alvo in _norm(o[0])]
    if not parecidas:
        raise ValueError(f"não achei a personagem `{nome}` (nem equipada, nem na coleção)")
    if len(parecidas) > 1:
        raise ValueError("mais de uma personagem bate com esse nome: " + ", ".join(o[0] for o in parecidas[:5]))
    return parecidas[0]


def _alt_main(u: dict, a: list[str], modo_alt: str) -> tuple[str, str, str]:
    if not a:
        raise ValueError(f"Uso: `{modo_alt} [nome da Main] <valor>`")
    nome, holder = _achar_main(u, " ".join(a[:-1]))
    modo, v = parse_valor(a[-1])
    atual = float(holder.get("love", 0.0))
    if modo_alt == "amor":
        novo = _aplicar(atual, modo, v, 0, MAX_FLOAT, "float")
        holder["love"] = float(novo)
    else:  # nivel
        n_atual = nivel(atual)[0]
        n_novo = _aplicar(n_atual, modo, v, 1, NIVEL_MAX, "int")
        novo = float(limiar(n_novo)) if n_novo != n_atual else atual
        holder["love"] = novo
    return (
        f"❤️ {'Amor' if modo_alt == 'amor' else 'Nível'} de {nome}",
        f"{fmt(atual)} pts (Nv {nivel(atual)[0]})",
        f"{fmt(novo)} pts (Nv {nivel(novo)[0]})",
    )


def _alt_item(u: dict, a: list[str]) -> tuple[str, str, str]:
    if len(a) < 2:
        raise ValueError("Uso: `item <chave> <valor>`")
    chave = next((k for k in ITEMS if _norm(k) == _norm(a[0])), None)
    if chave is None:
        raise ValueError("item inválido. Chaves: " + ", ".join(ITEMS))
    modo, v = parse_valor(a[1])
    atual = u["items"].get(chave, 0)
    novo = _aplicar(atual, modo, v, 0, MAX_ITEM, "int")
    if novo:
        u["items"][chave] = novo
    else:
        u["items"].pop(chave, None)
    it = ITEMS[chave]
    return f"{it['emoji']} {it['nome']}", f"x{atual}", f"x{novo}"


def _alt_hab(u: dict, a: list[str]) -> tuple[str, str, str]:
    if len(a) < 2:
        raise ValueError("Uso: `habilidade <id> <nível>`")
    chave = next((k for k in PRESTIGIO if _norm(k) == _norm(a[0])), None)
    if chave is None:
        raise ValueError("habilidade inválida. Ids: " + ", ".join(PRESTIGIO))
    emoji, nome, _, max_lv, _ = PRESTIGIO[chave]
    modo, v = parse_valor(a[1])
    atual = u["prest"].get(chave, 0)
    novo = _aplicar(atual, modo, v, 0, max_lv, "int")
    if novo:
        u["prest"][chave] = novo
    else:
        u["prest"].pop(chave, None)
    return f"{emoji} {nome}", f"Nv {atual}", f"Nv {novo}/{max_lv}"


def _cooldown(u: dict, a: list[str]) -> tuple[str, str, str]:
    qual = _norm(a[0]) if a else "todos"
    campos = {"trabalhar": "t_trab", "encontro": "t_enc", "duelo": "t_duelo", "diario": "diario"}
    if qual in ("todos", "todas", "all"):
        nomes = list(campos)
    elif qual in campos:
        nomes = [qual]
    else:
        raise ValueError("espera inválida. Use: trabalhar, encontro, duelo, diario ou todos")
    for n in nomes:
        if n == "diario":
            if u["diario"]:  # mantém a sequência, só libera o resgate
                u["diario"] = time.time() - DIARIO_ESPERA - 1
        else:
            u[campos[n]] = 0
    return "⏱️ Esperas", "em andamento", "zerada(s): " + ", ".join(nomes)


def _executar(u: dict, args: list[str]) -> tuple[str, str, str]:
    """Aplica uma alteração e devolve (título, antes, depois). Erros viram ValueError."""
    sub = _norm(args[0])
    if sub in ("cooldown", "cd", "espera"):
        return _cooldown(u, args[1:])
    if sub in ("item", "upgrade"):
        return _alt_item(u, args[1:])
    if sub in ("habilidade", "hab", "skill"):
        return _alt_hab(u, args[1:])
    if sub in ("amor", "love"):
        return _alt_main(u, args[1:], "amor")
    if sub in ("nivel", "level", "lv"):
        return _alt_main(u, args[1:], "nivel")
    c = CAMPO_POR_NOME.get(sub)
    if c is None:
        raise ValueError(f"o campo `{args[0]}` não existe (veja `$help`)")
    if len(args) < 2:
        raise ValueError(f"faltou o valor de `{c.nome}`")
    modo, v = parse_valor(args[1])
    atual = u[c.chave] / c.escala
    novo = _aplicar(atual, modo, v, c.minimo, c.maximo, c.tipo)
    u[c.chave] = novo * c.escala if c.escala != 1 else novo
    return c.rotulo, _txt_valor(c, atual), _txt_valor(c, novo)


async def _rp(message: discord.Message, texto: str | None = None, embed: discord.Embed | None = None) -> None:
    await message.reply(
        content=texto[:1990] if texto else None,
        embed=embed,
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )


def _embed_ver(u: dict, uid: int) -> discord.Embed:
    cls = classe_de(u["cp"])
    e = discord.Embed(title="🛠️ Estatísticas", description=f"<@{uid}>", color=ROSA)
    e.add_field(name="💰 Dinheiro", value=f"R$ {fmt(u['money'])}\nAcumulado: R$ {fmt(u['tot_money'])}")
    e.add_field(name="🏆 Classe", value=f"{cls[2]} {cls[1]}\n{fmt(u['cp'])} pts")
    e.add_field(
        name="📈 Bônus",
        value=f"💰 {fmt(u['b_lucro'])}% • ❤️ {fmt(u['b_amor'])}%\n🔁 Renasc.: {u['renasc']} • 🌳 gastos: {u['prest_gasto']}",
    )
    e.add_field(
        name="🎮 Jogo",
        value=(
            f"🎟️ Slots: {u['slots']}/{MAX_SLOTS} • 💠 {u['fragmentos']}\n"
            f"🔥 Streak: {u['streak']} (máx {u['max_streak']}) • 🍷 {u['n_enc']} encontros • 🎁 {u['n_pres']}\n"
            f"⚔️ {u['vitorias']}V/{u['derrotas']}D • ⏳ {fmt(u['t_jogo'] / 3600)} h"
        ),
        inline=False,
    )
    itens = " • ".join(f"{ITEMS[k]['emoji']} x{q}" for k, q in u["items"].items() if q and k in ITEMS)
    e.add_field(name="🛒 Upgrades", value=(itens or "nenhum")[:1000], inline=False)
    mains = "\n".join(f"⭐ {m['name']} — Nv {nivel(m['love'])[0]} ({fmt(m['love'])} pts)" for m in u["waifus"])
    e.add_field(name="💖 Mains", value=(mains or "nenhuma")[:1000], inline=False)
    return e


async def _membro_no_servidor(guild: discord.Guild, uid: int) -> bool:
    if guild.get_member(uid) is not None:
        return True
    try:
        await guild.fetch_member(uid)
        return True
    except discord.HTTPException:
        return False


async def cmd_change(message: discord.Message, args: list[str]) -> None:
    if len(args) < 2:
        await _rp(message, "Uso: `$change <@user|id|todos> <campo> <valor>` — veja `$help`.")
        return
    guild = message.guild
    alvo_txt, resto = args[0], args[1:]
    todos = _norm(alvo_txt) in ("todos", "all")
    ver = _norm(resto[0]) == "ver"
    if todos:
        if ver:
            await _rp(message, "❌ `ver` só funciona com um user específico.")
            return
        uids = [int(k) for k, u in store.data.items() if u.get("guild") == guild.id]
        if not uids:
            await _rp(message, "❌ Ninguém jogou neste servidor ainda.")
            return
    else:
        achou = re.search(r"\d{15,20}", alvo_txt)
        if achou is None:
            await _rp(message, "❌ Alvo inválido. Use uma menção, um ID ou `todos`.")
            return
        uid = int(achou.group())
        if not await _membro_no_servidor(guild, uid):
            await _rp(message, "❌ Esse user não está neste servidor.")
            return
        uids = [uid]

    if ver:
        async with store.lock:
            u = store.user(uids[0])
            embed = _embed_ver(u, uids[0]) if u is not None else None
        if embed is None:
            await _rp(message, "❌ Esse user ainda não começou o jogo.")
        else:
            await _rp(message, embed=embed)
        return

    ok: list[tuple[int, tuple[str, str, str]]] = []
    erros: list[str] = []
    async with store.lock:
        for uid in uids:
            u = store.user(uid)  # credita o que ele ganhou até agora antes de mexer
            if u is None:
                erros.append(f"<@{uid}>: ainda não começou o jogo")
                continue
            try:
                titulo, antes, depois = _executar(u, resto)
            except ValueError as exc:
                erros.append(f"<@{uid}>: {exc}")
                continue
            logar(u, f"🛠️ Ajuste do admin — {titulo}: {antes} → {depois}")
            processar_niveis(u)  # recalcula níveis/classe/conquistas normalmente
            ok.append((uid, (titulo, antes, depois)))
        if ok:
            store.save()

    linhas: list[str] = []
    if ok:
        uid0, (titulo, antes, depois) = ok[0]
        if todos:
            linhas.append(f"✅ **{titulo}** alterado em **{len(ok)}** player(s). Ex.: <@{uid0}> {antes} → {depois}")
        else:
            linhas.append(f"✅ <@{uid0}> — **{titulo}**: {antes} → {depois}")
    if erros:
        linhas.append("⚠️ " + "\n⚠️ ".join(erros[:8]) + (f"\n… e mais {len(erros) - 8}" if len(erros) > 8 else ""))
    await _rp(message, "\n".join(linhas))


def _blocos(linhas: list[str], limite: int = 1000) -> list[str]:
    """Junta linhas em blocos que cabem num field de embed."""
    out, atual = [], ""
    for ln in linhas:
        if atual and len(atual) + len(ln) + 1 > limite:
            out.append(atual)
            atual = ""
        atual += ("\n" if atual else "") + ln
    if atual:
        out.append(atual)
    return out


def _embed_help() -> discord.Embed:
    e = discord.Embed(
        title="🛠️ $change — ajuda",
        description=(
            "Altera qualquer estatística de qualquer player **do servidor atual**.\n"
            "Comando oculto: não aparece nos `/` e só você consegue usar."
        ),
        color=ROSA,
    )
    e.add_field(
        name="📌 Formato",
        value=(
            "`$change <alvo> <campo> <valor>`\n"
            "**Alvo:** `@user`, o ID do user, ou `todos` (todo mundo que joga neste servidor).\n"
            "O user precisa ser membro do servidor e já ter começado o jogo."
        ),
        inline=False,
    )
    e.add_field(
        name="🔢 Valores",
        value=(
            "`500` ou `=500` → define o valor\n"
            "`+500` → soma • `-500` → subtrai\n"
            "Atalhos: `k`/`mil`, `m`/`mi`, `b`/`bi`, `tri`, `quad`, `quint`, `sext` "
            "(ex.: `+2,5bi`, `10k`, `1e9`). Decimal com `,` ou `.`.\n"
            "Nunca fica negativo e cada campo tem um teto."
        ),
        inline=False,
    )
    linhas = [f"`{c.nome}` — {c.desc}" for c in CAMPOS]
    for i, bloco in enumerate(_blocos(linhas)):
        e.add_field(name="📊 Campos" if i == 0 else "📊 Campos (cont.)", value=bloco, inline=False)
    e.add_field(
        name="🧰 Subcomandos",
        value=(
            "`item <chave> <qtd>` — quantidade de um upgrade da loja\n"
            "`habilidade <id> <nível>` — nível de uma habilidade do /prestigio\n"
            "`amor [Main] <valor>` — pontos de amor de uma Main (equipada ou da coleção); sem nome = a 1ª Main\n"
            "`nivel [Main] <1-25>` — põe a Main num nível (ajusta o amor para o mínimo dele)\n"
            "`cooldown [trabalhar|encontro|duelo|diario|todos]` — zera as esperas\n"
            "`ver` — mostra as estatísticas do user"
        ),
        inline=False,
    )
    e.add_field(
        name="🔑 Chaves de upgrades",
        value=(", ".join(f"`{k}`" for k in ITEMS) + "\n**Habilidades:** " + ", ".join(f"`{k}`" for k in PRESTIGIO))[:1000],
        inline=False,
    )
    e.add_field(
        name="💡 Exemplos",
        value=(
            "`$change @fulano dinheiro +5mi`\n"
            "`$change @fulano slots 3`\n"
            "`$change @fulano item bico +50`\n"
            "`$change @fulano amor Rem +10000`\n"
            "`$change @fulano nivel Rem 25`\n"
            "`$change @fulano cooldown todos`\n"
            "`$change todos fragmentos +50`\n"
            "`$change @fulano ver`"
        ),
        inline=False,
    )
    e.add_field(
        name="⚠️ Observações",
        value=(
            "• Depois de cada alteração o jogo recalcula níveis, classe e conquistas (recompensas normais podem cair).\n"
            "• Cada ajuste fica registrado no `/historico` do player.\n"
            "• `todos` pega quem usou o bot por último neste servidor."
        ),
        inline=False,
    )
    return e


async def tratar_prefixo(message: discord.Message) -> None:
    """Chamado em toda mensagem; só reage a $change e $help do CHANGE_USER_ID."""
    if message.author.bot or message.guild is None or message.author.id != CHANGE_USER_ID:
        return
    txt = message.content.strip()
    if not txt.startswith(PREFIXO):
        return
    partes = txt[len(PREFIXO):].replace('"', "").replace("“", "").replace("”", "").split()
    if not partes:
        return
    cmd, args = partes[0].lower(), partes[1:]
    try:
        if cmd == "change":
            await cmd_change(message, args)
        elif cmd == "help":
            await _rp(message, embed=_embed_help())
    except Exception as exc:  # não deixa o bot calar se algo der errado
        import traceback

        traceback.print_exc()
        try:
            await _rp(message, f"❌ Erro inesperado: `{exc}`")
        except discord.HTTPException:
            pass



# ----------------------------------------------------------------------------
# Música (Lavalink/Lavahost via Wavelink)
# ----------------------------------------------------------------------------
def _player_do_guild(guild: discord.Guild) -> wavelink.Player | None:
    player = guild.voice_client
    return player if isinstance(player, wavelink.Player) else None


@bot.tree.command(name="play", description="Toca uma música ou pesquisa pelo nome")
@app_commands.describe(busca="Nome da música ou link")
@app_commands.guild_only()
async def play_cmd(interaction: discord.Interaction, busca: str):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Esse comando só funciona dentro de um servidor.", ephemeral=True
        )
        return

    if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
        await interaction.response.send_message(
            "Entra em um canal de voz primeiro, parça.", ephemeral=True
        )
        return

    canal = interaction.user.voice.channel
    await interaction.response.defer()

    player = _player_do_guild(interaction.guild)
    try:
        if player is None:
            player = await canal.connect(cls=wavelink.Player)
        elif player.channel != canal:
            await interaction.followup.send(
                f"Já estou em {player.channel.mention}. Entra nesse canal para pedir músicas."
            )
            return

        resultados = await wavelink.Playable.search(busca)
        if not resultados:
            await interaction.followup.send(
                "Não achei essa música. Tenta outro nome ou um link direto."
            )
            return

        faixa = resultados[0]
        await player.play(faixa)
        await interaction.followup.send(
            f"🎶 Tocando agora: **{faixa.title}**"
            + (f" — {faixa.author}" if getattr(faixa, "author", None) else "")
            + (f"\n{faixa.uri}" if getattr(faixa, "uri", None) else "")
        )
    except Exception as exc:
        print(f"[música] Erro em /play: {exc}")
        await interaction.followup.send(
            "Não consegui tocar essa música. Confere se o Lavalink/Lavahost está ativo e configurado."
        )


@bot.tree.command(name="pause", description="Pausa a música atual")
@app_commands.guild_only()
async def pause_cmd(interaction: discord.Interaction):
    player = _player_do_guild(interaction.guild) if interaction.guild else None
    if player is None or not player.playing:
        await interaction.response.send_message("Não tem música tocando agora.", ephemeral=True)
        return
    await player.pause(True)
    await interaction.response.send_message("⏸️ Música pausada.")


@bot.tree.command(name="resume", description="Continua a música pausada")
@app_commands.guild_only()
async def resume_cmd(interaction: discord.Interaction):
    player = _player_do_guild(interaction.guild) if interaction.guild else None
    if player is None or not player.paused:
        await interaction.response.send_message("Não tem música pausada agora.", ephemeral=True)
        return
    await player.pause(False)
    await interaction.response.send_message("▶️ Música retomada.")


@bot.tree.command(name="skip", description="Pula a música atual")
@app_commands.guild_only()
async def skip_cmd(interaction: discord.Interaction):
    player = _player_do_guild(interaction.guild) if interaction.guild else None
    if player is None or not player.playing:
        await interaction.response.send_message("Não tem música tocando agora.", ephemeral=True)
        return
    await player.skip()
    await interaction.response.send_message("⏭️ Música pulada.")


@bot.tree.command(name="stop", description="Para a música e desconecta do canal de voz")
@app_commands.guild_only()
async def stop_cmd(interaction: discord.Interaction):
    player = _player_do_guild(interaction.guild) if interaction.guild else None
    if player is None:
        await interaction.response.send_message("Não estou em um canal de voz.", ephemeral=True)
        return
    canal = getattr(player, "channel", None)
    if canal is not None:
        await bot.atualizar_status_voz(canal.id, "")
    await player.disconnect()
    await interaction.response.send_message("⏹️ Música parada; saí do canal de voz.")



if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Defina a variável DISCORD_TOKEN (no ambiente ou num arquivo .env).")
    bot.run(TOKEN)
