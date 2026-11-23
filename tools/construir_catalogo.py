#!/usr/bin/env python3
"""
Construye catalogo.json y estado.json para el Cotizador Hergom Vet
a partir del texto de la lista de precios (hoja "Veterinaria").

Fuente actual: "LISTA VET.xlsx" (OneDrive de ventasvet), una lista ligera sin imágenes.
El texto es la hoja tal como la entrega el conector de Microsoft 365: filas separadas por
saltos de línea y celdas separadas por tabuladores. Se acepta con o sin las líneas de
encabezado del conector ("## Sheet: ... — N rows × M columns").

Uso:
  construir_catalogo.py construir --json resultado_guardado.json --modificado 2026-11-20T15:37:48Z \
        --fuente "LISTA VET.xlsx" [--dir .] [--prueba]
  construir_catalogo.py construir --tsv lista.txt --modificado ISO --fuente "LISTA VET.xlsx"
  construir_catalogo.py estado --resultado sin_cambios|error --mensaje "..." \
        [--modificado ISO] [--dir .] [--prueba]

  --json  lee directamente el archivo donde el conector guardó una respuesta grande
          (lista de {type, text}); no hay que copiar nada a mano.
  --tsv   texto pegado a mano (solo si la respuesta llegó en línea).

Excepciones (tools/excepciones.json, junto a este script):
  "precios":    {"CLAVE": {"pp": 2645}}  precio de respaldo, SOLO si la celda de la lista no trae número
               (si la lista ya trae el número, manda la lista y queda un aviso para quitar la excepción).
  "cotizables": ["CLAVE"]  se publica sin precio y marcado "cotizable": true aunque la lista diga
               "¡Próximamente!" o "Cotizable"; el vendedor captura el precio en la partida.

Salidas (en --dir): catalogo.json (solo en "construir") y estado.json.
Con --prueba se escriben catalogo-prueba.json y estado-prueba.json y no se tocan los reales.

Protecciones: la lista nueva NO se publica si
  - no se encuentra el encabezado (Clave / Precio Distribuidor / Precio Público),
  - trae menos de 100 productos o menos del 70% de los que ya estaban publicados,
  - con --json: las filas recibidas no coinciden con las que declara el conector,
  - con --tsv: no hay fila TOTAL que coincida con la suma de precios (detecta dígitos mal copiados).
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
MAX_DIF_SIN_TOTAL = 12  # copia manual sin fila TOTAL: máximo de diferencias (contra lo publicado) que se pueden revisar una por una


def norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s).strip().lower()


def parse_dinero(s):
    """'$1.574.213,10' -> 1574213.10 ; '$517,24' -> 517.24 ; '1,574,213.10' -> 1574213.10 ; '1574213,103' -> 1574213.103 ; vacío -> None.

    Un solo separador seguido de exactamente 3 dígitos es de miles ('1,574' -> 1574) solo si lo que está antes mide de 1 a 3 dígitos
    y no es cero; si no ('1574213,103', '17241,376', '0,500') es decimal. Las listas sin formato de moneda traen números así."""
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
        # varios separadores iguales => miles; un solo separador con 3 dígitos después => miles solo si antes hay 1 a 3 dígitos (no cero)
        if len(partes) == 2:
            miles = len(partes[1]) == 3 and 1 <= len(partes[0]) <= 3 and partes[0].strip('0') != ''
            dec = None if miles else sep
        else:
            dec = None
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
            elif c.startswith('cat') and 'general' in c and 'cat' not in col:
                col['cat'] = j  # tolera erratas como "CATERGORÍA GENERAL"
            elif c in ('nota', 'notas') and 'nota' not in col:
                col['nota'] = j
            elif 'distribuidor' in c and 'con iva' not in c and 'pd' not in col:
                col['pd'] = j
            elif 'publico' in c and 'pp' not in col:
                col['pp'] = j
        if 'pd' in col and 'pp' in col:
            return i, col
    return None, None


def cargar_excepciones(ruta_exc=None):
    """Lee tools/excepciones.json (junto a este script). Formato:
      {"precios": {"CLAVE": {"pp": 2645, "pd": 1000, "motivo": "..."}},   # solo se usan si la celda de la lista no trae número
       "cotizables": ["CLAVE", ...]}                                       # se publican sin precio, como "cotizable"
    Si el archivo no existe o está mal formado, no hay excepciones."""
    ruta_exc = ruta_exc or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'excepciones.json')
    d = leer_json(ruta_exc) if os.path.exists(ruta_exc) else None
    precios, cotizables = {}, set()
    if isinstance(d, dict):
        for k, v in (d.get('precios') or {}).items():
            if isinstance(v, dict):
                ok = {f: float(v[f]) for f in ('pp', 'pd') if isinstance(v.get(f), (int, float)) and v[f] > 0}
                if ok:
                    precios[str(k).strip().upper()] = ok
        cotizables = {str(c).strip().upper() for c in (d.get('cotizables') or []) if str(c).strip()}
    return {'precios': precios, 'cotizables': cotizables}


def procesar(texto, excep=None, previo=None):
    excep = excep or {'precios': {}, 'cotizables': set()}
    # lo ya publicado, por clave: si la lista ya no trae la columna de categoría o de notas, se conserva lo anterior
    prev = {p['clave'].upper(): p for p in (previo or {}).get('productos', [])}
    seccion = ''
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
            if not clave and 'desc' in col and f[col['desc']].strip():
                seccion = re.sub(r'\s+', ' ', f[col['desc']]).strip()  # fila de sección (por ejemplo "RAYOS X")
            continue
        filas_datos += 1
        k = clave.upper()
        # precios de respaldo (tools/excepciones.json): solo si la celda no trae un número
        for campo, etiqueta in (('pp', 'público'), ('pd', 'distribuidor')):
            resp = excep['precios'].get(k, {}).get(campo)
            if not resp:
                continue
            if campo == 'pp' and not pp_v:
                pp_v = resp
                avisos.append('Precio %s de %s tomado de tools/excepciones.json: la celda de la lista no trae número' % (etiqueta, clave))
            elif campo == 'pd' and not pd_v:
                pd_v = resp
                avisos.append('Precio %s de %s tomado de tools/excepciones.json: la celda de la lista no trae número' % (etiqueta, clave))
            else:
                avisos.append('Ya puedes quitar la excepción de precio %s de %s en tools/excepciones.json: la lista ya trae el número' % (etiqueta, clave))
        cotizable = False
        if not pd_v and not pp_v:
            if k in excep['cotizables']:
                cotizable = True  # se publica sin precio, marcado como cotizable
            else:
                txt_precio = norm(f[col['pd']]) + ' ' + norm(f[col['pp']])
                if 'cotizable' in txt_precio or 'proximamente' in txt_precio:
                    continue  # "COTIZABLE" / "¡Próximamente!": todavía no tiene precio de lista
                avisos.append('Sin precio: ' + clave)
                continue
        elif k in excep['cotizables']:
            avisos.append('Ya puedes quitar a %s de "cotizables" en tools/excepciones.json: la lista ya trae precio' % clave)
        item = {
            'clave': clave,
            'desc': re.sub(r'\s+', ' ', f[col['desc']]).strip() if 'desc' in col else '',
            'marca': f[col['marca']].strip() if 'marca' in col else '',
            'cat': f[col['cat']].strip() if 'cat' in col else (prev.get(clave.upper(), {}).get('cat') or seccion),
            'pp': round(pp_v, 2) if pp_v else 0,
            'pd': round(pd_v, 2) if pd_v else 0,
        }
        if 'nota' in col:
            if f[col['nota']].strip():
                item['nota'] = f[col['nota']].strip()
        elif prev.get(clave.upper(), {}).get('nota'):
            item['nota'] = prev[clave.upper()]['nota']
        if cotizable:
            item['cotizable'] = True
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
        if p.get('cotizable'):
            continue
        if not p['pp']:
            avisos.append('Falta el precio público (revisa la celda): ' + p['clave'])
        elif not p['pd']:
            avisos.append('Falta el precio distribuidor (revisa la celda): ' + p['clave'])
    avisos = list(dict.fromkeys(avisos))  # sin repetidos, conservando el orden
    chk = {'sumaPD': round(suma_pd, 2), 'sumaPP': round(suma_pp, 2), 'totalPD': total_pd, 'totalPP': total_pp}
    return productos, avisos, chk


def verificar_filas(texto):
    """Compara las filas que trae el texto con las que declara el conector ("N rows x M columns").
    Devuelve (ok, mensaje); ok=None si el texto no trae esa declaración (copia manual)."""
    m = re.search(r'##\s*Sheet:.*?—\s*(\d+)\s*rows', texto)
    if not m:
        return None, ''
    declaradas = int(m.group(1))
    lineas = texto.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    ini = next((i for i, l in enumerate(lineas) if l.startswith('## Sheet:')), None)
    cuerpo = []
    for l in lineas[ini + 1:]:
        if l.startswith('Formulas:'):
            break
        cuerpo.append(l)
    while cuerpo and not cuerpo[0].strip():
        cuerpo.pop(0)  # línea en blanco entre el título de la hoja y las filas
    n = 0
    for l in cuerpo:
        mm = re.fullmatch(r'\[(\d+) empty rows?\]', l.strip())
        n += int(mm.group(1)) if mm else 1
    if n != declaradas:
        return False, 'La lectura parece incompleta: la hoja declara %d filas y el texto trae %d.' % (declaradas, n)
    return True, 'filas completas: %d de %d' % (n, declaradas)


def verificar_total(chk, directo=False, filas=(None, '')):
    if chk['totalPD'] is None and chk['totalPP'] is None:
        if directo and filas[0]:
            return True, 'Lectura directa del conector, sin fila TOTAL en la hoja (' + filas[1] + ')'
        return False, 'La hoja no trae fila TOTAL: no se pudo verificar la copia.'
    errs = []
    if chk['totalPD'] is not None and abs(chk['sumaPD'] - chk['totalPD']) > TOLERANCIA_TOTAL:
        errs.append('precio distribuidor: las filas suman %.2f y la hoja dice %.2f' % (chk['sumaPD'], chk['totalPD']))
    if chk['totalPP'] is not None and abs(chk['sumaPP'] - chk['totalPP']) > TOLERANCIA_TOTAL:
        errs.append('precio público: las filas suman %.2f y la hoja dice %.2f' % (chk['sumaPP'], chk['totalPP']))
    if errs:
        return False, 'La suma de las filas no coincide con el TOTAL de la hoja (' + '; '.join(errs) + '). Posible dígito mal copiado.'
    return True, 'Total verificado'


SALTO_SOSPECHOSO = 10  # un precio que se multiplica o divide por 10 o más casi seguro es un error de lectura, no un cambio de precio


def saltos_sospechosos(previo, productos):
    """Claves cuyo precio cambió 10 veces o más frente a lo publicado (por ejemplo 17241.38 -> 17241376 por leer mal 17241,376)."""
    if not previo:
        return []
    ant = {p['clave'].upper(): p for p in previo.get('productos', [])}
    malos = []
    for p in productos:
        q = ant.get(p['clave'].upper())
        if not q:
            continue
        for campo in ('pp', 'pd'):
            a, n = q.get(campo, 0), p.get(campo, 0)
            if a and n and (n >= a * SALTO_SOSPECHOSO or n <= a / SALTO_SOSPECHOSO):
                malos.append('%s %s %s -> %s' % (p['clave'], campo, a, n))
    return malos


def comparar(previo, productos):
    """Diferencias entre lo ya publicado y la lista nueva. Devuelve (cambios, detalle)."""
    cambios = {'nuevos': 0, 'quitados': 0, 'precios': 0, 'textos': 0}
    detalle = []
    if not previo:
        return cambios, detalle
    ant = {p['clave'].upper(): p for p in previo.get('productos', [])}
    nue = {p['clave'].upper(): p for p in productos}
    for k, p in nue.items():
        q = ant.get(k)
        if not q:
            cambios['nuevos'] += 1
            detalle.append('NUEVO    %s | pp %s | pd %s | %s' % (p['clave'], p['pp'], p['pd'], p['desc'][:70]))
            continue
        if abs(q.get('pp', 0) - p['pp']) > 0.005 or abs(q.get('pd', 0) - p['pd']) > 0.005:
            cambios['precios'] += 1
            detalle.append('PRECIO   %s | pp %s -> %s | pd %s -> %s' % (p['clave'], q.get('pp', 0), p['pp'], q.get('pd', 0), p['pd']))
        elif (q.get('desc'), q.get('marca'), q.get('cat')) != (p['desc'], p['marca'], p['cat']):
            cambios['textos'] += 1
            campos = [c for c, v in (('desc', 'desc'), ('marca', 'marca'), ('cat', 'cat')) if q.get(c) != p[c]]
            detalle.append('TEXTO    %s | cambió: %s | ahora: %s' % (p['clave'], ', '.join(campos), ' / '.join(str(p[c])[:70] for c in campos)))
    for k, q in ant.items():
        if k not in nue:
            cambios['quitados'] += 1
            detalle.append('QUITADO  %s | %s' % (q['clave'], str(q.get('desc', ''))[:70]))
    return cambios, detalle


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


def leer_texto_json(ruta_json):
    """Lee el resultado de read_resource que la herramienta guardó en un archivo (lista de {type, text}),
    o un texto plano. Así no hay que copiar la hoja a mano."""
    raw = open(ruta_json, encoding='utf-8').read()
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(d, dict):
        d = d.get('content', d)
        if isinstance(d, dict):
            return d.get('text', raw)
    if isinstance(d, list):
        return ''.join(x.get('text', '') for x in d if isinstance(x, dict) and x.get('type', 'text') == 'text')
    return raw


def cmd_construir(a):
    directo = bool(a.json)
    texto = leer_texto_json(a.json) if directo else open(a.tsv, encoding='utf-8').read()
    fuente_mod = a.modificado
    try:
        filas_ok, filas_msg = verificar_filas(texto)
        if filas_ok is False:
            raise ValueError(filas_msg)
        previo = leer_json(ruta(a.dir, 'catalogo.json', a.prueba))
        productos, avisos, chk = procesar(texto, cargar_excepciones(a.excepciones), previo)
        ok_total, msg_total = verificar_total(chk, directo, (filas_ok, filas_msg))
        n_prev = len(previo.get('productos', [])) if previo else 0
        cambios, detalle = comparar(previo, productos)
        n_dif = sum(cambios.values())
        # Copia manual sin fila TOTAL: cualquier dígito mal copiado aparece como una diferencia contra lo ya publicado,
        # así que se puede verificar revisando esas diferencias una por una contra la lectura original.
        if not ok_total and not directo and filas_ok is True and previo and msg_total.startswith('La hoja no trae fila TOTAL'):
            if n_dif == 0:
                ok_total, msg_total = True, 'Copia manual sin fila TOTAL, idéntica a lo ya publicado (filas completas: %s)' % filas_msg
            elif n_dif <= MAX_DIF_SIN_TOTAL:
                if a.diferencias_verificadas:
                    ok_total, msg_total = True, 'Copia manual sin fila TOTAL: %d diferencias revisadas una por una contra la lectura del conector' % n_dif
                else:
                    print('REVISA %d diferencias contra la lectura ORIGINAL del conector (no contra tu copia):' % n_dif)
                    for d in detalle:
                        print('  ' + d)
                    print('Si todas coinciden con la lectura original, repite el mismo comando agregando --diferencias-verificadas.')
                    print('Si alguna no coincide, corrige tu copia y vuelve a ejecutar (no publiques nada todavía).')
                    return 3
            else:
                msg_total = ('La hoja no trae fila TOTAL y hay %d diferencias frente a lo publicado (más de %d), demasiadas para revisarlas una por una. '
                             'Agrega una fila TOTAL a la lista (suma de PD y PP).' % (n_dif, MAX_DIF_SIN_TOTAL))
        problemas = []
        saltos = saltos_sospechosos(previo, productos)
        if saltos:
            problemas.append('Precios que cambian %d veces o más (probable error al leer los números): %s.' % (SALTO_SOSPECHOSO, '; '.join(saltos[:5])))
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
        'avisos': avisos[:30],
        'verificacion': msg_total,
    })
    print('OK: %d productos · %s · cambios %s · avisos %d' % (len(productos), msg_total, cambios, len(avisos)))
    for av in avisos[:30]:
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
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument('--tsv', help='texto de la hoja copiado a un archivo')
    g.add_argument('--json', help='archivo donde la herramienta guardó el resultado de read_resource (sin copiar a mano)')
    c.add_argument('--modificado', default='')
    c.add_argument('--fuente', default='Lista Precios Hergom Vet - 2026.xlsx')
    c.add_argument('--dir', default='.')
    c.add_argument('--diferencias-verificadas', action='store_true', help='copia manual sin fila TOTAL: ya revisé cada diferencia contra la lectura original')
    c.add_argument('--excepciones', default=None, help='ruta de excepciones.json (por omisión, el de tools/)')
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
