#!/usr/bin/env python3
"""
Construye catalogo.json y estado.json para el Cotizador Hergom Vet
a partir del texto de la lista maestra de precios.

El texto es la hoja "Veterinaria" de "Lista Precios Hergom Vet - 2026.xlsx" tal como la
entrega el conector de Microsoft 365: filas separadas por saltos de línea y celdas
separadas por tabuladores. Se acepta con o sin las líneas de encabezado del conector.

Uso:
  construir_catalogo.py construir --tsv lista.tsv --modificado 2026-11-06T20:40:37Z \
        --fuente "Lista Precios Hergom Vet - 2026.xlsx" [--dir .] [--prueba]
  construir_catalogo.py estado --resultado sin_cambios|error --mensaje "..." \
        [--modificado ISO] [--dir .] [--prueba]

Salidas (en --dir): catalogo.json (solo en "construir") y estado.json.
Con --prueba se escriben catalogo-prueba.json y estado-prueba.json y no se tocan los reales.

Protecciones: la lista nueva NO se publica si
  - no se encuentra el encabezado (Clave / Precio Distribuidor / Precio Público),
  - trae menos de 100 productos o menos del 70% de los que ya estaban publicados,
  - la suma de precios de las filas no coincide con la fila TOTAL de la propia hoja
    (detecta cualquier dígito mal copiado).
En esos casos se conserva el catalogo.json anterior y estado.json queda con resultado "error".
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

MIN_PRODUCTOS = 100
MIN_FRACCION_PREVIA = 0.70
TOLERANCIA_TOTAL = 1.0  # pesos


def norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s).strip().lower()


def parse_dinero(s):
    """'$1.574.213,10' -> 1574213.10 ; '$517,24' -> 517.24 ; '1,574,213.10' -> 1574213.10 ; vacío -> None."""
    t = str(s or '').strip()
    if not t:
        return None
    t = re.sub(r'[^\d.,\-]', '', t)
    if not t or not re.search(r'\d', t):
        return None
    neg = t.startswith('-')
    t = t.replace('-', '')
    pd, pc = t.rfind('.'), t.rfind(',')
    if pd >= 0 and pc >= 0:
        dec = '.' if pd > pc else ','
    elif pd >= 0 or pc >= 0:
        sep = '.' if pd >= 0 else ','
        partes = t.split(sep)
        # varios separadores iguales, o 3 dígitos tras el único separador => miles
        dec = sep if (len(partes) == 2 and len(partes[1]) != 3) else None
    else:
        dec = None
    if dec:
        ent, frac = t.rsplit(dec, 1)
        ent = re.sub(r'[.,]', '', ent)
        t = ent + '.' + frac
    else:
        t = re.sub(r'[.,]', '', t)
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def leer_filas(texto):
    filas = []
    for linea in texto.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if linea.startswith('Formulas:'):
            break
        if '\t' in linea:
            celdas = linea.split('\t')
        elif '¦' in linea:
            celdas = linea.split('¦')
        else:
            celdas = [linea]
        filas.append([c.strip() for c in celdas])
    return filas


def buscar_encabezado(filas):
    for i, f in enumerate(filas):
        n = [norm(c) for c in f]
        if 'clave' not in n:
            continue
        col = {'clave': n.index('clave')}
        for j, c in enumerate(n):
            if c.startswith('descripcion') and 'desc' not in col:
                col['desc'] = j
            elif c == 'marca' and 'marca' not in col:
                col['marca'] = j
            elif c.startswith('categoria general') and 'cat' not in col:
                col['cat'] = j
            elif c == 'categoria' and 'cat' not in col:
                col['cat'] = j
            elif 'distribuidor' in c and 'con iva' not in c and 'pd' not in col:
                col['pd'] = j
            elif 'publico' in c and 'pp' not in col:
                col['pp'] = j
        if 'pd' in col and 'pp' in col:
            return i, col
    return None, None


def procesar(texto):
    filas = leer_filas(texto)
    ih, col = buscar_encabezado(filas)
    if ih is None:
        raise ValueError('No encontré el encabezado (Clave / Precio Distribuidor / Precio Público) en el texto de la lista.')
    ancho = max(col.values()) + 1
    productos, vistos, avisos = [], {}, []
    suma_pd = suma_pp = 0.0
    total_pd = total_pp = None
    filas_datos = 0
    for f in filas[ih + 1:]:
        f = f + [''] * (ancho - len(f))
        if any(norm(c) == 'total' for c in f):
            total_pd = parse_dinero(f[col['pd']])
            total_pp = parse_dinero(f[col['pp']])
            break
        pd_v, pp_v = parse_dinero(f[col['pd']]), parse_dinero(f[col['pp']])
        if pd_v:
            suma_pd += pd_v
        if pp_v:
            suma_pp += pp_v
        clave = f[col['clave']].strip()
        if not clave or norm(clave) == 'clave':
            continue
        filas_datos += 1
        if not pd_v and not pp_v:
            avisos.append('Sin precio: ' + clave)
            continue
        item = {
            'clave': clave,
            'desc': re.sub(r'\s+', ' ', f[col['desc']]).strip() if 'desc' in col else '',
            'marca': f[col['marca']].strip() if 'marca' in col else '',
            'cat': f[col['cat']].strip() if 'cat' in col else '',
            'pp': round(pp_v, 2) if pp_v else 0,
            'pd': round(pd_v, 2) if pd_v else 0,
        }
        k = clave.upper()
        if k in vistos:
            ant = vistos[k]
            if abs(ant['pp'] - item['pp']) > 0.005 or abs(ant['pd'] - item['pd']) > 0.005:
                avisos.append('Clave repetida con precios distintos (se usa la primera): ' + clave)
            continue
        vistos[k] = item
        productos.append(item)
    for p in productos:
        if p['pd'] and p['pp'] and p['pd'] > p['pp'] * 1.0001:
            avisos.append('Precio distribuidor mayor que el público: ' + p['clave'])
    chk = {'sumaPD': round(suma_pd, 2), 'sumaPP': round(suma_pp, 2), 'totalPD': total_pd, 'totalPP': total_pp}
    return productos, avisos, chk


def verificar_total(chk):
    if chk['totalPD'] is None and chk['totalPP'] is None:
        return False, 'La hoja no trae fila TOTAL: no se pudo verificar la copia.'
    errs = []
    if chk['totalPD'] is not None and abs(chk['sumaPD'] - chk['totalPD']) > TOLERANCIA_TOTAL:
        errs.append('precio distribuidor: las filas suman %.2f y la hoja dice %.2f' % (chk['sumaPD'], chk['totalPD']))
    if chk['totalPP'] is not None and abs(chk['sumaPP'] - chk['totalPP']) > TOLERANCIA_TOTAL:
        errs.append('precio público: las filas suman %.2f y la hoja dice %.2f' % (chk['sumaPP'], chk['totalPP']))
    if errs:
        return False, 'La suma de las filas no coincide con el TOTAL de la hoja (' + '; '.join(errs) + '). Posible dígito mal copiado.'
    return True, 'Total verificado'


def ahora():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def ruta(dir_, nombre, prueba):
    if prueba:
        nombre = nombre.replace('.json', '-prueba.json')
    return os.path.join(dir_, nombre)


def leer_json(p):
    try:
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return None


def escribir_json(p, obj, compacto=False):
    with open(p, 'w', encoding='utf-8') as fh:
        if compacto:
            json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write('\n')


def escribir_estado(dir_, prueba, resultado, mensaje='', modificado='', extra=None):
    previo = leer_json(ruta(dir_, 'estado.json', prueba)) or {}
    est = {
        'revisado': ahora(),
        'resultado': resultado,
        'mensaje': mensaje,
        'fuenteModificado': modificado or previo.get('fuenteModificado', ''),
        'fuente': previo.get('fuente', ''),
        'productos': previo.get('productos', 0),
        'cambios': previo.get('cambios', {}),
        'avisos': previo.get('avisos', []),
    }
    if extra:
        est.update(extra)
    escribir_json(ruta(dir_, 'estado.json', prueba), est)
    return est


def cmd_construir(a):
    texto = open(a.tsv, encoding='utf-8').read()
    fuente_mod = a.modificado
    try:
        productos, avisos, chk = procesar(texto)
        ok_total, msg_total = verificar_total(chk)
        previo = leer_json(ruta(a.dir, 'catalogo.json', a.prueba))
        n_prev = len(previo.get('productos', [])) if previo else 0
        problemas = []
        if len(productos) < MIN_PRODUCTOS:
            problemas.append('Solo %d productos (se esperaban al menos %d).' % (len(productos), MIN_PRODUCTOS))
        if n_prev and len(productos) < n_prev * MIN_FRACCION_PREVIA:
            problemas.append('Bajó de %d a %d productos (más del 30%%): no se publica.' % (n_prev, len(productos)))
        if not ok_total:
            problemas.append(msg_total)
        if problemas:
            raise ValueError(' '.join(problemas))
    except Exception as e:
        escribir_estado(a.dir, a.prueba, 'error', str(e))
        print('ERROR:', e, file=sys.stderr)
        return 2

    # diferencias contra lo ya publicado
    cambios = {'nuevos': 0, 'quitados': 0, 'precios': 0, 'textos': 0}
    if previo:
        ant = {p['clave'].upper(): p for p in previo.get('productos', [])}
        nue = {p['clave'].upper(): p for p in productos}
        cambios['nuevos'] = len([k for k in nue if k not in ant])
        cambios['quitados'] = len([k for k in ant if k not in nue])
        for k, p in nue.items():
            q = ant.get(k)
            if not q:
                continue
            if abs(q.get('pp', 0) - p['pp']) > 0.005 or abs(q.get('pd', 0) - p['pd']) > 0.005:
                cambios['precios'] += 1
            elif (q.get('desc'), q.get('marca'), q.get('cat')) != (p['desc'], p['marca'], p['cat']):
                cambios['textos'] += 1
    cat = {
        'ok': True,
        'version': 1,
        'actualizado': fuente_mod or ahora(),
        'generado': ahora(),
        'fuente': a.fuente,
        'productos': productos,
    }
    escribir_json(ruta(a.dir, 'catalogo.json', a.prueba), cat, compacto=True)
    est = escribir_estado(a.dir, a.prueba, 'ok', '', fuente_mod, {
        'fuente': a.fuente,
        'productos': len(productos),
        'cambios': cambios,
        'avisos': avisos[:20],
        'verificacion': msg_total,
    })
    print('OK: %d productos · %s · cambios %s · avisos %d' % (len(productos), msg_total, cambios, len(avisos)))
    for av in avisos[:20]:
        print('  aviso:', av)
    return 0


def cmd_estado(a):
    escribir_estado(a.dir, a.prueba, a.resultado, a.mensaje or '', a.modificado or '')
    print('estado.json:', a.resultado, a.mensaje or '')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('construir')
    c.add_argument('--tsv', required=True)
    c.add_argument('--modificado', default='')
    c.add_argument('--fuente', default='Lista Precios Hergom Vet - 2026.xlsx')
    c.add_argument('--dir', default='.')
    c.add_argument('--prueba', action='store_true')
    c.set_defaults(fn=cmd_construir)
    e = sub.add_parser('estado')
    e.add_argument('--resultado', required=True, choices=['sin_cambios', 'error', 'ok'])
    e.add_argument('--mensaje', default='')
    e.add_argument('--modificado', default='')
    e.add_argument('--dir', default='.')
    e.add_argument('--prueba', action='store_true')
    e.set_defaults(fn=cmd_estado)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == '__main__':
    main()
