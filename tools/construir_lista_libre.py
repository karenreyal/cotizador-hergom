#!/usr/bin/env python3
"""Convierte una lista de precios en Excel a lista-libre.json: marca, descripción y precios de productos que
NO están en el catálogo de Vet (LISTA VET). El cotizador los usa para llenar solo una partida libre al escribir la clave.

La hoja debe traer una fila de encabezados con las columnas CLAVE, NOMBRE (o DESCRIPCIÓN), MARCA, PD y PP
(el orden no importa; pueden sobrar columnas como IMAGEN, EAN o SUB CATEGORÍA; las filas de sección, sin clave, se saltan).

Uso:
  python3 tools/construir_lista_libre.py ARCHIVO.xlsx --fuente "LP HANDY Mayo 2026"

--fuente es el nombre de esa lista. Si vuelves a correrlo con el mismo nombre, esa lista se reemplaza completa (así una
lista actualizada no deja claves viejas); con otro nombre se suma a lo que ya había (si una clave sale en las dos, gana la nueva).
Los precios se redondean a centavos; "-", vacío o 0 quedan como "sin precio".
"""
import argparse
import datetime
import json
import os
import re
import sys
import unicodedata

import openpyxl

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, 'lista-libre.json')


def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn').upper().strip()


def numero(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    else:
        s = re.sub(r'[\s$]', '', str(x))
        if s.count(',') == 1 and s.count('.') == 0:
            s = s.replace(',', '.')            # 1574,21 -> 1574.21
        else:
            s = s.replace(',', '')
        try:
            v = float(s)
        except ValueError:
            return None
    v = round(v + 1e-9, 2)
    return v if v > 0 else None


def limpiar(t):
    return re.sub(r'\s+', ' ', str(t or '')).strip()


def leer(ruta, fuente):
    wb = openpyxl.load_workbook(ruta, data_only=True)
    productos, avisos = {}, []
    hojas = 0
    for ws in wb.worksheets:
        fila_enc, cols = None, {}
        for i, r in enumerate(ws.iter_rows(min_row=1, max_row=25, values_only=True), start=1):
            celdas = [norm(c) for c in r]
            if 'CLAVE' in celdas:
                fila_enc = i
                for j, c in enumerate(celdas):
                    if c == 'CLAVE': cols['clave'] = j
                    elif c.startswith('NOMBRE') or c.startswith('DESCRIP'): cols.setdefault('desc', j)
                    elif c == 'MARCA': cols['marca'] = j
                    elif c.startswith('PD'): cols.setdefault('pd', j)
                    elif c.startswith('PP'): cols.setdefault('pp', j)
                break
        if not fila_enc:
            continue
        faltan = [k for k in ('clave', 'desc', 'marca', 'pd', 'pp') if k not in cols]
        if faltan:
            avisos.append(f'hoja "{ws.title}": falta la columna {", ".join(faltan)}; se salta')
            continue
        hojas += 1
        for i, r in enumerate(ws.iter_rows(min_row=fila_enc + 1, values_only=True), start=fila_enc + 1):
            clave = re.sub(r'\s+', ' ', str(r[cols['clave']] or '')).strip().upper()
            if not clave:
                continue
            marca = limpiar(r[cols['marca']]).upper()
            desc = limpiar(r[cols['desc']])
            pd, pp = numero(r[cols['pd']]), numero(r[cols['pp']])
            nuevo = [marca, desc, pd, pp, fuente]
            if clave in productos:
                ant = productos[clave]
                if ant[2:4] != nuevo[2:4]:
                    avisos.append(f'clave repetida con precios distintos ({clave}, fila {i}): se usa la primera')
                continue
            productos[clave] = nuevo
            if pd is None and pp is None:
                avisos.append(f'{clave} (fila {i}): sin precio PD ni PP')
            elif pd is None:
                avisos.append(f'{clave} (fila {i}): sin PD (solo PP {pp})')
            elif pp is None:
                avisos.append(f'{clave} (fila {i}): sin PP (solo PD {pd})')
            elif pp < pd:
                avisos.append(f'{clave} (fila {i}): PP {pp} menor que PD {pd}')
            elif pp / pd > 3:
                avisos.append(f'{clave} (fila {i}): PP {pp} es {pp / pd:.1f} veces PD {pd}; revisa si es correcto')
    if not hojas:
        raise SystemExit('ERROR: no encontré una hoja con encabezados CLAVE, NOMBRE/DESCRIPCIÓN, MARCA, PD y PP.')
    return productos, avisos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('xlsx')
    ap.add_argument('--fuente', required=True, help='nombre de esta lista, por ejemplo "LP HANDY Mayo 2026"')
    ap.add_argument('--salida', default=SALIDA)
    a = ap.parse_args()

    nuevos, avisos = leer(a.xlsx, a.fuente)
    previos = {}
    if os.path.exists(a.salida):
        with open(a.salida, encoding='utf-8') as f:
            previos = (json.load(f).get('productos')) or {}
    # una lista actualizada reemplaza a la anterior con el mismo nombre
    conservados = {k: v for k, v in previos.items() if (v[4] if len(v) > 4 else '') != a.fuente}
    pisadas = [k for k in nuevos if k in conservados]
    productos = {**conservados, **nuevos}

    fuentes = {}
    for v in productos.values():
        fuentes[v[4]] = fuentes.get(v[4], 0) + 1
    salida = {
        'ok': True,
        'actualizado': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'fuentes': [{'nombre': n, 'productos': c} for n, c in sorted(fuentes.items())],
        'productos': dict(sorted(productos.items())),
    }
    with open(a.salida, 'w', encoding='utf-8') as f:
        json.dump(salida, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    print(f'{len(nuevos)} claves de "{a.fuente}" · total en {os.path.basename(a.salida)}: {len(productos)}')
    if pisadas:
        print(f'  aviso: {len(pisadas)} claves ya estaban en otra lista y se reemplazaron: {", ".join(pisadas[:10])}')
    for t in avisos:
        print('  aviso:', t)


if __name__ == '__main__':
    sys.exit(main())
