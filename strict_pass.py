import json, os, re, time, urllib.request

DATA = "/tmp/corte3/prototipo/data"
OR_KEY = open("/tmp/corte3/prototipo/openrouter_key.txt").read().strip()
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen-2.5-72b-instruct"
TOK = {"in": 0, "out": 0}
WORKER = int(os.environ.get("WORKER", "0")); NWORKERS = int(os.environ.get("NWORKERS", "1"))
RF = f"/tmp/corte3/prototipo/resultados_strict_w{WORKER}.json"

def orchat(prompt, max_tokens=220):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": "Bearer " + OR_KEY, "Content-Type": "application/json"})
    for intento in range(4):
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=180).read())
            u = d.get("usage", {})
            TOK["in"] += u.get("prompt_tokens", 0); TOK["out"] += u.get("completion_tokens", 0)
            return d["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            print("HTTP", e.code, flush=True)
            if e.code not in (429, 500, 502, 503, 529): return None
            time.sleep(5 * (intento + 1))
        except Exception as e:
            print("error:", e, flush=True); time.sleep(5 * (intento + 1))
    return None

def parsej(t):
    if not t: return None
    m = re.search(r"\{[^{}]*\}", t, re.S)
    if not m: return None
    try:
        d = json.loads(m.group(0))
        if d.get("riesgo") in ("bajo", "revisar"): return d
    except Exception: pass
    return None

P = """Eres auditor senior de glosas de una clinica colombiana. Tu trabajo es DECIDIR si esta historia sera glosada por la EPS.
Dato clave: solo ~10% de las historias del lote tienen glosa real. Una primera pasada liberal marco esta historia como "{causa_prev}" (motivo: {motivo_prev}). Tu trabajo es CONFIRMAR solo si la evidencia es concluyente y DESCARTAR ante cualquier duda razonable.

Reglas estrictas:
- "cie10": solo si el texto clinico contradice CLARAMENTE el diagnostico que corresponde al codigo CIE-10 facturado (cita la contradiccion). Que la historia sea breve o generica NO es glosa.
- "soporte": solo si el texto dice EXPLICITAMENTE que falta un documento obligatorio (epicrisis, consentimiento, ayuda diagnostica, nota operatoria) o es evidente que el procedimiento facturado no tiene soporte alguno. Ausencia de mencion de un soporte no es prueba de que falte.
- "tarifa": el cruce deterministico con el contrato dice: {cruce}. Confia en ese cruce, no inventes diferencias.
- Si el procedimiento facturado no aparece en la historia clinica como realizado/ordenado, eso SI es evidencia fuerte (soporte).
Responde SOLO un JSON: {{"riesgo":"bajo"|"revisar","causa":"cie10"|"soporte"|"tarifa"|"ninguna","motivo":"<max 20 palabras>","evidencia":"<cita corta del texto o 'regla tarifa'>"}}

Tipo: {tipo} | EPS: {eps} | CIE-10 facturado: {cie} | Procedimiento: {proc} | Valor facturado: {valor} COP | Valor contrato: {contrato}
Historia:
{texto}"""

def main():
    tarifas = json.load(open(f"{DATA}/tarifas.json"))
    prev = {p["id"]: p for p in json.load(open("/tmp/corte3/prototipo/envio_merged.json"))["predicciones"]}
    res, done = [], set()
    if os.path.exists(RF):
        try:
            d = json.load(open(RF)); res = d.get("predicciones", [])
            done = {r["id"] for r in res}; TOK.update(d.get("tokens", {}))
            print("reanudando:", len(done), flush=True)
        except Exception: res, done = [], set()
    ids = [i for n, i in enumerate(sorted(prev)) if n % NWORKERS == WORKER]
    for hid in ids:
        if hid in done: continue
        det = json.load(open(f"{DATA}/det_{hid}.json"))
        if det.get("escaneada"):
            oc = f"{DATA}/ocr_{hid}.json"
            texto = json.load(open(oc))["texto"] if os.path.exists(oc) else ""
        else:
            texto = det.get("texto") or ""
        t = tarifas.get("eps", {}).get(det["eps"], {}).get(det["procedimiento"])
        contrato = t["valor_cop"] if t else None
        if t:
            dif = abs(t["valor_cop"] - det["valor_cop"]) / t["valor_cop"] * 100
            cruce = f"valor facturado {det['valor_cop']} vs contrato {t['valor_cop']} (diferencia {dif:.1f}%)" + (" -> GLOSA por tarifa" if dif > 10 else " -> coincide, sin glosa tarifa")
        else:
            cruce = "procedimiento no encontrado en la tabla de tarifas del contrato (posible glosa: no contratado)"
        p0 = prev[hid]
        prompt = P.format(causa_prev=p0.get("causa", "?"), motivo_prev=p0.get("motivo", "")[:80],
                          tipo=det["tipo"], eps=det["eps"], cie=det["cie10_facturado"],
                          proc=det["procedimiento"], valor=det["valor_cop"],
                          contrato=contrato if contrato else "N/D", cruce=cruce,
                          texto=texto[:3000])
        d = parsej(orchat(prompt))
        if not d:
            d = {"riesgo": p0["prioridad"], "causa": p0.get("causa", "ninguna"), "motivo": "fallback etapa estricta", "evidencia": ""}
        # regla deterministica tarifa manda si diferencia > 10%
        if t and abs(t["valor_cop"] - det["valor_cop"]) > 0.10 * t["valor_cop"]:
            d = {"riesgo": "revisar", "causa": "tarifa",
                 "motivo": f"valor {det['valor_cop']} vs tarifa contrato {t['valor_cop']}", "evidencia": "regla tarifa"}
        res.append({"id": hid, "prioridad": d["riesgo"], "causa": d.get("causa", "ninguna"),
                    "motivo": d.get("motivo", ""), "evidencia": d.get("evidencia", "")[:200],
                    "escaneada": bool(det.get("escaneada"))})
        json.dump({"tokens": TOK, "predicciones": res}, open(RF + ".tmp", "w"), ensure_ascii=False, indent=2)
        os.replace(RF + ".tmp", RF)
        if len(res) % 20 == 0:
            rev = sum(1 for r in res if r["prioridad"] == "revisar")
            print(f"{len(res)}/300 revisar={rev} tokens in={TOK['in']:,}", flush=True)
    json.dump({"tokens": TOK, "predicciones": res}, open(RF, "w"), ensure_ascii=False, indent=2)
    print("FIN", TOK, flush=True)

main()
