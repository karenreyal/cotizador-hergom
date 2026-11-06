# Informe de prueba del robot (2026-11-06)

(a) Herramientas: Microsoft 365 (sharepoint_search, sharepoint_folder_search, read_resource y de escritura/Outlook/Teams), diferidas, cargadas con ToolSearch. Repositorio: el clon ya existía en la sesión (origin = karenreyal/cotizador-hergom); add_repo/register_repo_root no hicieron falta. Herramientas mcp__github__* disponibles; se usó git por Bash.
(b) Lectura OK con read_resource (startPage 1, endPage 1): hoja "Veterinaria", 233 filas x 9 columnas. La copia a TSV tiene 231 líneas / 33886 caracteres (del encabezado a TOTAL; se omitieron los marcadores "[1 empty row]" del conector).
(c) Los tabuladores se conservaron al escribir con Write (verificado con grep/cat -A).
(d) Salida del script construir:
```
OK: 159 productos · Total verificado · cambios {'nuevos': 0, 'quitados': 0, 'precios': 0, 'textos': 0} · avisos 14
  aviso: Clave repetida con precios distintos (se usa la primera): C11-3S
  aviso: Clave repetida con precios distintos (se usa la primera): P10-4SV
  aviso: Clave repetida con precios distintos (se usa la primera): P8-2S
  aviso: Clave repetida con precios distintos (se usa la primera): C11-3S
  aviso: Clave repetida con precios distintos (se usa la primera): P10-4SV
  aviso: Clave repetida con precios distintos (se usa la primera): P8-2S
  aviso: Clave repetida con precios distintos (se usa la primera): L13-3NS
  aviso: Clave repetida con precios distintos (se usa la primera): C11-3S
  aviso: Clave repetida con precios distintos (se usa la primera): P10-4SV
  aviso: Clave repetida con precios distintos (se usa la primera): P8-2S
  aviso: Clave repetida con precios distintos (se usa la primera): L13-3NS
  aviso: Clave repetida con precios distintos (se usa la primera): C11-3S
  aviso: Clave repetida con precios distintos (se usa la primera): P10-4SV
  aviso: Clave repetida con precios distintos (se usa la primera): P8-2S
```
(e) Intentos de copia: 1 (sin reintentos). Código de salida 0.
(f) Fricciones: ninguna de permisos ni de tiempo. Notas: la hoja trae una 9a columna con valores sueltos (p. ej. $35.100,00 y $403.750,00) y 14 avisos de claves repetidas con precios distintos (el script usa la primera). Se escribió la lista en 2 partes (lista_1.tsv, lista_2.tsv) y se unió con cat.
