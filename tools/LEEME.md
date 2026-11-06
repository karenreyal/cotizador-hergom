# Actualización automática de la lista de precios

El cotizador (`index.html`) abre primero `catalogo.json` y `estado.json`, que viven junto a la página.
Un robot (tarea programada de Claude, ver `PROMPT_ROBOT.md`) los mantiene al día:

1. Revisa la fecha de modificación de la lista maestra de SharePoint
   (`Lista Precios Hergom Vet - 2026.xlsx`, carpeta DRIVE COMERCIAL HERGOM / 01 LISTAS DE PRECIOS GENERAL / VETERINARIA).
2. Si cambió, la lee con el conector de Microsoft 365 de la cuenta de Karen (no se usa Power Automate, ni Azure, ni nada que requiera permisos de TI).
3. `python3 tools/construir_catalogo.py construir ...` convierte el texto en `catalogo.json` y solo lo publica si pasa las verificaciones:
   la suma de precios de las filas debe coincidir con la fila TOTAL de la propia hoja, no puede bajar más de 30% el número de productos, etc.
4. Hace commit y push; GitHub Pages lo publica en 1 o 2 minutos.

Si algo falla, se conserva el `catalogo.json` anterior y `estado.json` queda con `"resultado": "error"`; la página lo muestra en naranja.
Si el robot deja de correr más de 60 horas, la página también avisa.

## Límite importante
El conector de Microsoft 365 solo lee archivos de hasta 100 MB. Si la lista maestra pasa de ese tamaño (casi siempre por imágenes pesadas),
el robot no puede leerla y lo reporta en `estado.json`. Solución: en Excel, clic en una imagen > Formato de imagen > Comprimir imágenes >
quitar la marca de "Aplicar solo a esta imagen" > resolución Web (150 ppi) o menor > Aceptar > guardar.

## Archivos
- `catalogo.json`: productos (clave, descripción, marca, categoría, precio público con IVA `pp`, precio distribuidor sin IVA `pd`) y la fecha de la lista maestra (`actualizado`).
- `estado.json`: última revisión, resultado (`ok`, `sin_cambios`, `error`), mensaje, cambios (nuevos, quitados, precios, textos) y avisos (por ejemplo, PD mayor que PP).
- `tools/construir_catalogo.py`: convierte y verifica. Con `--prueba` escribe archivos `*-prueba.json` sin tocar los reales.

Las fotos no viajan en el catálogo automático: siguen incrustadas en `index.html` por clave (un producto nuevo sale con un ícono hasta que se agregue su foto).
