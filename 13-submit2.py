import json, sys, time, requests

BASE = "https://labs.proyectoasur.org/api/clinica"
tok = json.load(open("token_equipo.json"))["respuesta"]
TOKEN = tok.get("token") or tok.get("access_token")
prev = {p["id"]: p for p in json.load(open("envio_merged.json"))["predicciones"]}
preds = json.load(open("strict_merged.json"))["predicciones"]

MAPA = {"soporte": "falta_soporte", "tarifa": "tarifa_incorrecta", "cie10": "codigo_incorrecto"}

def build(mapa):
    items = []
    for p in preds:
        hid = p["id"]
        if hid == 258:  # fallback con dif 0% -> bajo
            riesgo, causa, motivo = "bajo", None, "valor coincide con tarifa del contrato"
        else:
            riesgo = p["prioridad"]
            causa = mapa.get(p["causa"]) if riesgo == "revisar" else None
            motivo = (p.get("motivo") or "")[:150]
        if riesgo == "revisar" and not causa:
            causa = "falta_soporte"
        old = prev.get(hid, {})
        items.append({"id": hid, "riesgo": riesgo, "causa": causa, "motivo": motivo,
                      "tokens_entrada": old.get("tokens_entrada", 1500),
                      "tokens_salida": old.get("tokens_salida", 100)})
    return items

def enviar(items):
    H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
    r = requests.post(f"{BASE}/priorizacion", json=items, headers=H, timeout=60)
    return r.status_code, r.text

mapa = dict(MAPA)
if len(sys.argv) > 1 and sys.argv[1] == "allfalta":
    mapa = {"soporte": "falta_soporte", "tarifa": "falta_soporte", "cie10": "falta_soporte"}
items = build(mapa)
rev = sum(1 for i in items if i["riesgo"] == "revisar")
print("revisar:", rev, "| causas:", sorted({i["causa"] for i in items if i["causa"]}))
code, txt = enviar(items)
ts = time.strftime("%Y%m%d-%H%M%S")
open(f"envio_{ts}.json", "w").write(txt)
print("HTTP", code)
print(txt[:1500])
