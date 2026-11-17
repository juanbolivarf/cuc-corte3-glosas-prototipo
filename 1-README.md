# Prototipo Corte 3 - IA privada contra las glosas (JuanBolivar-24456)

Proyecto del tercer corte, Arquitectura en la Nube (CUC): un pipeline que lee las
300 historias clinicas de la API del curso, detecta posibles glosas (cargos a
revisar) con un modelo de lenguaje y envia las predicciones a
`POST /api/clinica/priorizacion`.

## Archivos

- `clinica_client.py`: registro del equipo, descarga de historias e imagenes, tarifas.
- `ocr.py`: OCR de las 60 historias escaneadas (Tesseract, espanol).
- `pipeline.py`: flujo en Ollama/EC2 (qwen2.5:1.5b + qwen2.5:3b) - corrida interrumpida por la caida del laboratorio.
- `pipeline_local.py`: pasada liberal con endpoint OpenAI-compatible (reanudable, 2 workers).
- `strict_pass.py`: pasada estricta con evidencia citada y tasa base (reanudable, 2 workers).
- `merge_submit.py` / `submit2.py`: armado del JSON de 300 predicciones y envio a la API.
- `envio_valido.json`, `envio_mejor.json`, `envio_20261116-104607_iter3.json`: respuestas crudas de la API de los envios de calibracion (17 y 19).
- `envio_20261116-233533_tokens_corregidos.json`: respuesta cruda del mejor envio (24).

## Como correrlo

1. Registrar el equipo con `clinica_client.py` (guarda `token_equipo.json`, no incluido aqui).
2. Bajar las historias y correr `ocr.py` sobre las imagenes.
3. Correr `pipeline_local.py` y luego `strict_pass.py` (necesitan una llave de un endpoint OpenAI-compatible en `/tmp/corte3/prototipo/openrouter_key.txt`, no incluida).
4. Armar el envio con `merge_submit.py` y enviar con `submit2.py`.

## Resultado del mejor envio

Envio 24, codigo de verificacion **CLX-24-89B0-7D0C** (recibido 2026-11-16 23:35 hora Bogota):

| Metrica | Valor |
| --- | --- |
| F1 (revisar) | 0.7895 |
| Precision (revisar) | 0.6522 |
| Recall (revisar) | 1.0 |
| Acierto de causa | 0.7333 |
| Matriz de confusion | VP 30, FP 16, FN 0, VN 254 |
| Tokens entrada / salida | 1,092,547 / 55,956 |

Los tokens y llaves NO se incluyen en este repositorio.
