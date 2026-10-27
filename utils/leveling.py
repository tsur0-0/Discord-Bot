def xp_for_level(n: int) -> int:
    """XP necessário para ir do nível n para n+1."""
    return 5 * n * n + 50 * n + 100


def level_from_xp(xp: int):
    """Retorna (nível, xp_no_nível, xp_necessário_para_o_próximo)."""
    level = 0
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
    return level, xp, xp_for_level(level)
