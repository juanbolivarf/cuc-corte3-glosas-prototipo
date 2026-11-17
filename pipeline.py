"""Pipeline Cap 6: replica del flujo del Cap 1 sobre las 300 historias de la API.

  descarga -> (OCR si escaneada) -> clasificador pequeno (bajo/revisar + causa)
           -> LLM grande solo para dudosas -> consolidar -> enviar (max 20/dia)

El backend del modelo es Ollama local (modelo de los labs del corte), URL por env OLLAMA_URL.
Contadores de tokens: los que reporta Ollama (prompt_eval_count / eval_count),
declarados en el envio como tokens de entrada y salida.
"""
import json, os, re, sys, time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clinica_client as api
from ocr import ocr_imagen

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODELO_PEQUENO = os.environ.get("MODELO_PEQUENO", "qwen2.5:1.5b-instruct-q4_K_M")
MODELO_GRANDE = os.environ.get("MODELO_GRANDE", "qwen2.5:7b-instruct-q4_K_M")
DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DIR, "data")
os.makedirs(DATA, exist_ok=True)

TOK = {"in": 0, "out": 0}

PROMPT_CLASIF = """Eres un auditor medico de una clinica colombiana. Lee la historia clinica y decide si tiene riesgo de GLOSA (objecion de la EPS a la factura).

Causas tipicas de glosa:
- "cie10": el codigo diagnostico CIE-10 no coincide con lo descrito en la historia.
- "soporte": falta soporte documental (examenes, consentimientos, epicrisis, notas de evolucion).
- "tarifa": valores o tarifas que no corresponden al contrato (usa las tarifas del contrato si se dan).

Responde SOLO un JSON en una linea:
{"prioridad": "bajo" | "revisar", "causa": "cie10" | "soporte" | "tarifa" | "ninguna", "motivo": "<max 20 palabras>"}

Historia:
{texto}"""

PROMPT_GRANDE = """Eres un auditor senior. Una primera revision marco esta historia como posible glosa por "{causa}". Confirmas o descartas?

Responde SOLO un JSON en una linea:
{"prioridad": "bajo" | "revisar", "causa": "cie10" | "soporte" | "tarifa" | "ninguna", "motivo": "<max 30 palabras>"}

Historia:
{texto}"""


def llamar(modelo, prompt):
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": modelo, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0}},
                      timeout=600)
    r.raise_for_status()
    d = r.json()
    TOK["in"] += d.get("prompt_eval_count", 0)
    TOK["out"] += d.get("eval_count", 0)
    return d["response"]


def parsear_json(txt):
    m = re.search(r"\{[^{}]*\}", txt, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        if d.get("prioridad") in ("bajo", "revisar"):
            d.setdefault("causa", "ninguna")
            return d
    except Exception:
        return None
    return None


def texto_de(h):
    """Texto de la historia: directo, u OCR si es escaneada."""
    det = h.get("detalle") or h
    if det.get("escaneada"):
        img = os.path.join(DATA, f"img_{h['id']}.png")
        if not os.path.exists(img):
            api.imagen(h["id"], img)
        txt, conf = ocr_imagen(img)
        h["ocr_confianza"] = conf
        return txt
    for k in ("texto", "contenido", "historia", "body"):
        if det.get(k):
            return det[k]
    return json.dumps(det, ensure_ascii=False)


def clasificar(h, usar_grande=True):
    texto = texto_de(h)
    d = parsear_json(llamar(MODELO_PEQUENO, PROMPT_CLASIF.format(texto=texto[:24000])))
    if d is None:  # salida no parseable -> revisar (prudente)
        d = {"prioridad": "revisar", "causa": "soporte", "motivo": "salida del clasificador no parseable"}
    h["etapa1"] = d
    # OCR de baja confianza -> cola humana siempre (Cap 0, obs. 4)
    if h.get("ocr_confianza") is not None and h["ocr_confianza"] < 60:
        d = {"prioridad": "revisar", "causa": "soporte", "motivo": f"OCR dudoso (confianza {h['ocr_confianza']:.0f})"}
    if usar_grande and d["prioridad"] == "revisar":
        g = parsear_json(llamar(MODELO_GRANDE, PROMPT_GRANDE.format(causa=d.get("causa", "?"), texto=texto[:24000])))
        if g:
            h["etapa2"] = g
            d = g
    h["prediccion"] = {"prioridad": d["prioridad"], "causa": d.get("causa", "ninguna")}
    return h


def main(limite=None, usar_grande=True):
    idx_path = os.path.join(DATA, "indice.json")
    if os.path.exists(idx_path):
        indice = json.load(open(idx_path))
    else:
        indice = api.listar_historias()
        json.dump(indice, open(idx_path, "w"), ensure_ascii=False, indent=2)
    historias = indice if isinstance(indice, list) else indice.get("historias", [])
    print(f"{len(historias)} historias en indice")

    resultados = []
    for i, h in enumerate(historias[:limite] if limite else historias):
        hid = h.get("id") or h.get("historia_id")
        cache = os.path.join(DATA, f"det_{hid}.json")
        if os.path.exists(cache):
            h = json.load(open(cache))
        else:
            h["id"] = hid
            h["detalle"] = api.detalle(hid)
            json.dump(h, open(cache, "w"), ensure_ascii=False, indent=2)
        h = clasificar(h, usar_grande=usar_grande)
        json.dump(h, open(cache, "w"), ensure_ascii=False, indent=2)
        resultados.append(h)
        if (i + 1) % 10 == 0:
            print(f"{i+1}/{len(historias)}  tokens acum: in={TOK['in']:,} out={TOK['out']:,}")
    json.dump({"tokens": TOK, "n": len(resultados)},
              open(os.path.join(DATA, "resumen_tokens.json"), "w"))
    print(f"FIN. Tokens: in={TOK['in']:,} out={TOK['out']:,}")
    return resultados


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(lim)
