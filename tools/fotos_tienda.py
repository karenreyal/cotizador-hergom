#!/usr/bin/env python3
"""Arma fotos-web.json (clave/SKU -> foto) leyendo la tienda de Hergom (Shopify).

La tienda publica sus productos en https://hergom-medical.com/products.json (50 a 250 por página):
cada producto trae sus variantes con `sku` (la clave) y sus fotos. Este script recorre todas las páginas
y guarda, por cada SKU, la foto de esa variante (o, si no tiene, la primera foto del producto).

El cotizador solo descarga este archivo (unos cuantos KB) y pide cada foto a la tienda cuando la necesita,
así que no importa qué tan grande sea la lista de precios.

Uso:
  python3 tools/fotos_tienda.py                 # lee la tienda y actualiza fotos-web.json si algo cambió
  python3 tools/fotos_tienda.py --desde pagina.json [otra.json ...]   # prueba con archivos en lugar de la tienda
  python3 tools/fotos_tienda.py --salida /tmp/prueba.json              # escribe en otro archivo

Seguridad: si la tienda no responde, responde vacía o trae menos de la mitad de las claves que ya había,
NO toca fotos-web.json y sale con error (así una falla de la tienda no borra las fotos que ya funcionaban).
Solo reescribe el archivo si las fotos cambiaron (no hay commits diarios sin cambios).
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

TIENDA = 'https://hergom-medical.com'
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, 'fotos-web.json')
POR_PAGINA = 250
MAX_PAGINAS = 60          # tope de seguridad (15,000 productos)


def pedir(url, intentos=3):
    ultimo = None
    for n in range(intentos):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'cotizador-hergom-fotos/1.0 (+https://karenreyal.github.io/cotizador-hergom/)',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            ultimo = e
            time.sleep(2 * (n + 1))
    raise RuntimeError(f'no se pudo leer {url}: {ultimo}')


def productos_de_la_tienda(tienda):
    todos = []
    for pagina in range(1, MAX_PAGINAS + 1):
        data = pedir(f'{tienda}/products.json?limit={POR_PAGINA}&page={pagina}')
        lote = data.get('products') or []
        if not lote:
            break
        todos.extend(lote)
        time.sleep(1)     # sin prisa: la tienda no se satura
    return todos


def productos_de_archivos(rutas):
    todos = []
    for r in rutas:
        with open(r, encoding='utf-8') as f:
            d = json.load(f)
        todos.extend(d.get('products') if isinstance(d, dict) else d)
    return todos


def construir(prods):
    """SKU (mayúsculas, sin espacios) -> URL de la foto."""
    fotos = {}
    for p in prods:
        imgs = [i for i in (p.get('images') or []) if isinstance(i, dict) and i.get('src')]
        por_id = {i.get('id'): i['src'] for i in imgs if i.get('id')}
        primera = imgs[0]['src'] if imgs else ''
        for v in p.get('variants') or []:
            sku = (v.get('sku') or '').strip().upper()
            if not sku:
                continue
            src = ''
            fi = v.get('featured_image')
            if isinstance(fi, dict):
                src = fi.get('src') or ''
            if not src and v.get('image_id'):
                src = por_id.get(v['image_id'], '')
            if not src:
                src = primera
            if src and sku not in fotos:       # si una clave se repite, gana la primera
                fotos[sku] = src
    return fotos


def con_base(fotos):
    """Quita el prefijo común de las URLs para que el archivo pese menos."""
    urls = list(fotos.values())
    if not urls:
        return '', {}
    base = os.path.commonprefix(urls)
    base = base[:base.rfind('/') + 1] if '/' in base else ''
    if base.count('/') < 4:          # solo "https://sitio/": no vale la pena
        return '', dict(fotos)
    return base, {k: v[len(base):] for k, v in fotos.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tienda', default=TIENDA)
    ap.add_argument('--desde', nargs='+', help='archivos products.json en lugar de leer la tienda')
    ap.add_argument('--salida', default=SALIDA)
    ap.add_argument('--forzar', action='store_true', help='escribe aunque traiga menos de la mitad de las claves anteriores')
    a = ap.parse_args()

    prods = productos_de_archivos(a.desde) if a.desde else productos_de_la_tienda(a.tienda)
    fotos = construir(prods)
    print(f'productos leídos: {len(prods)} · claves con foto: {len(fotos)}')
    if not fotos:
        print('ERROR: no llegó ninguna clave con foto; no se toca el archivo.', file=sys.stderr)
        return 1

    base, rel = con_base(fotos)
    anterior = {}
    if os.path.exists(a.salida):
        try:
            with open(a.salida, encoding='utf-8') as f:
                ant = json.load(f)
            b0 = ant.get('base') or ''
            anterior = {k: (v if v.startswith('http') else b0 + v) for k, v in (ant.get('fotos') or {}).items()}
        except (ValueError, OSError):
            anterior = {}
    if anterior and len(fotos) < len(anterior) * 0.5 and not a.forzar:
        print(f'ERROR: la tienda trae {len(fotos)} claves y ya había {len(anterior)}; '
              'no se toca el archivo (usa --forzar si es correcto).', file=sys.stderr)
        return 2
    if anterior == fotos:
        print('sin cambios en las fotos; no se reescribe fotos-web.json')
        return 0

    salida = {
        'ok': True,
        'actualizado': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'fuente': a.tienda,
        'claves': len(fotos),
        'base': base,
        'fotos': dict(sorted(rel.items())),
    }
    with open(a.salida, 'w', encoding='utf-8') as f:
        json.dump(salida, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    nuevas = len(set(fotos) - set(anterior))
    quitadas = len(set(anterior) - set(fotos))
    print(f'escrito {a.salida}: {len(fotos)} claves (nuevas {nuevas}, quitadas {quitadas})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
