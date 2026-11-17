# Codigo del prototipo - Capitulo 6 (JuanBolivar-24456)

- clinica_client.py: registro del equipo, descarga de historias e imagenes, tarifas.
- ocr.py: OCR de las 60 historias escaneadas (Tesseract, espanol).
- pipeline.py: flujo en Ollama/EC2 (qwen2.5:1.5b + qwen2.5:3b) - corrida interrumpida por la caida de Vocareum.
- pipeline_local.py: pasada liberal con endpoint OpenAI-compatible (reanudable, 2 workers).
- strict_pass.py: pasada estricta con evidencia citada y tasa base (reanudable, 2 workers).
- merge_submit.py / submit2.py: armado del JSON de 300 predicciones y envio a POST /api/clinica/priorizacion.
- envio_valido.json / envio_mejor.json / envio_20261116-104607_iter3.json: respuestas crudas de la API (envios 17 y 19).

Los tokens/llaves NO se incluyen.
