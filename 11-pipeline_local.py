import json, os, re, subprocess, time, urllib.request

DATA = "/tmp/corte3/prototipo/data"
OR_KEY = open("/tmp/corte3/prototipo/openrouter_key.txt").read().strip()
URL = "https://openrouter.ai/api/v1/chat/completions"
M1 = "qwen/qwen-2.5-72b-instruct"   # etapa 1
M2 = "qwen/qwen-2.5-72b-instruct"   # etapa 2
TOK = {"in": 0, "out": 0}
WORKER = int(os.environ.get("WORKER", "0")); NWORKERS = int(os.environ.get("NWORKERS", "1"))
RF = f"/tmp/corte3/prototipo/resultados_local_w{WORKER}.json" if NWORKERS > 1 else "/tmp/corte3/prototipo/resultados_local.json"

def orchat(model, prompt, max_tokens):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
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
            print("openrouter error:", e.code, flush=True)
            if e.code not in (429, 500, 502, 503, 529): return None
            time.sleep(5 * (intento + 1))
        except Exception as e:
            print("openrouter error:", e, flush=True); time.sleep(5 * (intento + 1))
    return None

def parsej(t):
    if not t: return None
    m = re.search(r"\{[^{}]*\}", t, re.S)
    if not m: return None
    try:
        d = json.loads(m.group(0))
        if d.get("prioridad") in ("bajo", "revisar"): return d
    except Exception: pass
    return None

def ocr(hid):
    fp = f"{DATA}/ocr_{hid}.json"
    if os.path.exists(fp):
        try: return json.load(open(fp))
        except Exception: pass
    p = f"{DATA}/img/img_{hid}.png"
    env = dict(os.environ, TESSDATA_PREFIX="/tmp/corte3/tessdata")
    subprocess.run(["tesseract", p, f"{DATA}/img/ocr_{hid}", "-l", "spa", "--psm", "6"],
                   capture_output=True, timeout=300, env=env)
    txt = open(f"{DATA}/img/ocr_{hid}.txt", encoding="utf-8", errors="ignore").read()
    d = {"id": hid, "texto": " ".join(txt.split())}
    json.dump(d, open(fp + ".tmp", "w"), ensure_ascii=False); os.replace(fp + ".tmp", fp)
    return d

P1 = """Eres auditor medico de una clinica colombiana. Decide si esta historia tiene riesgo de GLOSA (objecion de la EPS).
Causas: "cie10" (el codigo CIE-10 facturado no coincide con la historia), "soporte" (falta soporte documental: examenes, consentimiento, epicrisis, notas), "tarifa" (valor o procedimiento no corresponde).
Responde SOLO un JSON: {{"prioridad":"bajo"|"revisar","causa":"cie10"|"soporte"|"tarifa"|"ninguna","motivo":"<max 20 palabras>"}}

Tipo: {tipo} | EPS: {eps} | CIE-10 facturado: {cie} | Procedimiento: {proc} | Valor: {valor} COP
Historia:
{texto}"""

P2 = """Eres auditor senior. Una primera revision marco esta historia como posible glosa por "{causa}". Confirma o descarta. Si la causa era tarifa, considera que el valor facturado ya se cruzo con el contrato.
Responde SOLO un JSON: {{"prioridad":"bajo"|"revisar","causa":"cie10"|"soporte"|"tarifa"|"ninguna","motivo":"<max 30 palabras>"}}

Tipo: {tipo} | CIE-10 facturado: {cie} | Procedimiento: {proc} | Valor: {valor} COP
Historia:
{texto}"""

def main():
    tarifas = json.load(open(f"{DATA}/tarifas.json"))
    indice = json.load(open(f"{DATA}/indice.json"))
    res, done_ids = [], set()
    if os.path.exists(RF):
        try:
            prev = json.load(open(RF)); res = prev.get("predicciones", [])
            done_ids = {r["id"] for r in res}
            TOK.update(prev.get("tokens", {}))
            print("reanudando:", len(done_ids), flush=True)
        except Exception as e:
            print("resume fallo:", e, flush=True); res = []; done_ids = set()
    for i, h in enumerate(indice):
        hid = h["id"]
        if NWORKERS > 1 and i % NWORKERS != WORKER: continue
        if hid in done_ids: continue
        det = json.load(open(f"{DATA}/det_{hid}.json"))
        texto = ocr(hid)["texto"] if det.get("escaneada") else (det.get("texto") or "")
        base = dict(tipo=det["tipo"], eps=det["eps"], cie=det["cie10_facturado"],
                    proc=det["procedimiento"], valor=det["valor_cop"], texto=texto[:3000])
        t = tarifas.get("eps", {}).get(det["eps"], {}).get(det["procedimiento"])
        regla_tarifa = bool(t) and abs(t["valor_cop"] - det["valor_cop"]) > 0.10 * t["valor_cop"]
        d = parsej(orchat(M1, P1.format(**base), 140)) or \
            {"prioridad": "revisar", "causa": "soporte", "motivo": "salida no parseable"}
        if regla_tarifa:
            d = {"prioridad": "revisar", "causa": "tarifa",
                 "motivo": f"valor {det['valor_cop']} vs tarifa contrato {t['valor_cop']}"}
        if d["prioridad"] == "revisar":
            b2 = dict(base); b2["texto"] = base["texto"][:2500]
            g = parsej(orchat(M2, P2.format(causa=d.get("causa", "?"), **b2), 180))
            if regla_tarifa:
                d = {"prioridad": "revisar", "causa": "tarifa", "motivo": d.get("motivo", "regla tarifa")}
            elif g:
                d = g
        res.append({"id": hid, "prioridad": d["prioridad"], "causa": d.get("causa", "ninguna"),
                    "motivo": d.get("motivo", ""), "escaneada": bool(det.get("escaneada"))})
        json.dump({"tokens": TOK, "predicciones": res}, open(RF + ".tmp", "w"), ensure_ascii=False, indent=2)
        os.replace(RF + ".tmp", RF)
        if (len(res)) % 10 == 0:
            print(f"{len(res)}/300 tokens in={TOK['in']:,} out={TOK['out']:,}", flush=True)
    open("/tmp/corte3/prototipo/local.done", "w").write("done")
    print("FIN", TOK, flush=True)

main()
