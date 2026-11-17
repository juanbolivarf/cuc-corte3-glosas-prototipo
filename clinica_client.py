"""Cliente de la API de la Clinica Caribe Salud Integral (Proyecto Aula Corte 3).
Cap 6 - prototipo del flujo: OCR -> modelo pequeno -> modelo grande -> auditor (envio).
"""
import json, os, time
import requests

BASE = "https://labs.proyectoasur.org/api/clinica"
DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(DIR, "token_equipo.json")  # el token NO se puede recuperar; guardarlo


def registrar_equipo(nombre):
    """Una sola vez. Devuelve el token y lo guarda en disco."""
    if os.path.exists(TOKEN_FILE):
        raise SystemExit(f"Ya existe {TOKEN_FILE}; no registrar de nuevo.")
    r = requests.post(f"{BASE}/equipos", json={"nombre": nombre}, timeout=30)
    r.raise_for_status()
    data = r.json()
    with open(TOKEN_FILE, "w") as f:
        json.dump({"equipo": nombre, "respuesta": data}, f, ensure_ascii=False, indent=2)
    return data


def _token():
    data = json.load(open(TOKEN_FILE))
    resp = data["respuesta"]
    return resp.get("token") or resp.get("access_token") or resp.get("data", {}).get("token")


def _h():
    return {"Authorization": f"Bearer {_token()}"}


def listar_historias(tipo=None, escaneada=None):
    """Descarga el indice completo (300 historias) paginando."""
    out, pagina = [], 1
    while True:
        params = {"pagina": pagina, "tam": 100}
        if tipo: params["tipo"] = tipo
        if escaneada is not None: params["escaneada"] = str(escaneada).lower()
        r = requests.get(f"{BASE}/historias", headers=_h(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("historias") or data.get("items") or data.get("data") or data
        if isinstance(items, dict):  # formato inesperado: guardar crudo
            return data
        out.extend(items)
        total = data.get("total") if isinstance(data, dict) else None
        if len(items) < 100 or (total and len(out) >= total):
            return out
        pagina += 1


def detalle(historia_id):
    r = requests.get(f"{BASE}/historias/{historia_id}", headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json()


def imagen(historia_id, destino):
    r = requests.get(f"{BASE}/historias/{historia_id}/imagen", headers=_h(), timeout=60)
    r.raise_for_status()
    with open(destino, "wb") as f:
        f.write(r.content)
    return destino


def tarifas():
    r = requests.get(f"{BASE}/tarifas", headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json()


def enviar_priorizacion(predicciones):
    """predicciones: lista de dicts por historia. Guarda la respuesta cruda (codigo de verificacion)."""
    r = requests.post(f"{BASE}/priorizacion", headers=_h(), json=predicciones, timeout=120)
    ts = time.strftime("%Y%m%d-%H%M%S")
    with open(os.path.join(DIR, f"envio_{ts}.json"), "w") as f:
        json.dump({"status": r.status_code, "respuesta": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text}, f, ensure_ascii=False, indent=2)
    r.raise_for_status()
    return r.json()
