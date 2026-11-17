import json, glob, collections, sys
sys.path.insert(0, '/tmp/corte3/prototipo')
preds = {}
tok_in = tok_out = 0
for fp in sorted(glob.glob('/tmp/corte3/prototipo/resultados_*.json')):
    d = json.load(open(fp))
    tok_in += d['tokens']['in']; tok_out += d['tokens']['out']
    for p in d['predicciones']:
        preds[p['id']] = p
print('total predicciones:', len(preds), '| tokens in:', tok_in, '| out:', tok_out)
lista = [preds[i] for i in sorted(preds)]
dist = collections.Counter((p['prioridad'], p.get('causa')) for p in lista)
for k, v in sorted(dist.items()): print(f'  {k[0]:8s} {k[1]:8s} {v}')
json.dump({'predicciones': lista, 'tokens': {'in': tok_in, 'out': tok_out}},
          open('/tmp/corte3/prototipo/envio_merged.json', 'w'), ensure_ascii=False, indent=2)
print('guardado envio_merged.json')
