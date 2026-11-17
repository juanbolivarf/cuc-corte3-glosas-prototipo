"""Etapa 0 del flujo: OCR de historias escaneadas (20% del caso, 60 de las 300 de la API).
Tesseract con datos en espanol; umbral de confianza: si la confianza media es baja,
la historia va a cola humana (observacion 4 del Cap 0).
"""
import os
import pytesseract
from PIL import Image, ImageOps, ImageFilter

TESSDATA = os.environ.get("TESSDATA_PREFIX", "/tmp/corte3/tessdata")


def ocr_imagen(ruta, lang="spa"):
    """Devuelve (texto, confianza_media 0-100)."""
    img = Image.open(ruta)
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    # Preproceso: gris, autocontraste, leve enfoque
    gris = ImageOps.grayscale(img)
    gris = ImageOps.autocontrast(gris)
    gris = gris.filter(ImageFilter.SHARPEN)
    cfg = f'--tessdata-dir "{TESSDATA}"'
    data = pytesseract.image_to_data(gris, lang=lang, config=cfg, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, t in zip(data["conf"], data["text"]) if str(c) not in ("-1", "-1.0") and t.strip()]
    texto = " ".join(t for t in data["text"] if t.strip())
    conf = sum(confs) / len(confs) if confs else 0.0
    return texto, conf
