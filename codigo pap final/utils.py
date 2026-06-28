"""Funções auxiliares do Ticketline (gráficos, datas, ficheiros)."""
from datetime import datetime, timedelta


def allowed(filename, exts):
    """Verifica se a extensão do ficheiro é permitida."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def tempo_desde(dt_str):
    """Converte uma data da BD em texto legível (ex: 'há 5 minutos')."""
    if not dt_str:
        return "nunca"
    try:
        dt = datetime.strptime(str(dt_str)[:19], "%Y-%m-%d %H:%M:%S")
        segundos = (datetime.utcnow() - dt).total_seconds()
        if segundos < 60:
            return "agora mesmo"
        if segundos < 3600:
            m = int(segundos // 60)
            return f"há {m} minuto{'s' if m != 1 else ''}"
        if segundos < 86400:
            h = int(segundos // 3600)
            return f"há {h} hora{'s' if h != 1 else ''}"
        d = int(segundos // 86400)
        return f"há {d} dia{'s' if d != 1 else ''}"
    except ValueError:
        return "desconhecido"


def is_online(dt_str):
    """True se o utilizador acedeu nos últimos 5 minutos."""
    if not dt_str:
        return False
    try:
        dt = datetime.strptime(str(dt_str)[:19], "%Y-%m-%d %H:%M:%S")
        return datetime.utcnow() - dt < timedelta(minutes=5)
    except ValueError:
        return False


def chart_por_cat(rows):
    """Prepara dados para gráfico de categorias."""
    return {
        "labels": [r["categoria"].title() for r in rows],
        "values": [r["n"] for r in rows],
    }


def chart_por_estado(rows):
    """Prepara dados para gráfico de estados."""
    return {
        "labels": [r["estado"].replace("_", " ").title() for r in rows],
        "values": [r["n"] for r in rows],
    }


def chart_por_prio(rows):
    """Prepara dados para gráfico de prioridades."""
    return {
        "labels": [r["prioridade"].title() for r in rows],
        "values": [r["n"] for r in rows],
    }
