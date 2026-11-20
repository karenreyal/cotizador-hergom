# Actualización automática de la lista de precios

El cotizador (`index.html`) abre primero `catalogo.json` y `estado.json`, que viven junto a la página.
Un robot (tarea programada de Claude, ver `PROMPT_ROBOT.md`) los mantiene al día. Corre una vez al día, de lunes a sábado a las 6:47 p.m. (hora de Ciudad de México), después de que se actualiza la lista:

1. Lee `LISTA VET.xlsx` (OneDrive de ventasvet, https://byhergom-my.sharepoint.com/personal/ventasvet_byhergom_com/Documents/LISTA VET.xlsx)
   con el conector de Microsoft 365 de la cuenta de Karen (no se usa Power Automate, ni Azure, ni nada que requiera permisos de TI).
   No se fía de la fecha de modificación que da el buscador de SharePoint, porque puede ir horas atrasada: siempre lee el archivo.
2. Compara contra lo ya publicado. Si no hay diferencias, no vuelve a publicar la lista y solo actualiza `estado.json` (la fecha de la última revisión).
3. `python3 tools/construir_catalogo.py construir ...` convierte el texto en `catalogo.json` y solo lo publica si pasa las verificaciones:
   debe traer todas las filas que declara el conector, encontrar el encabezado, no puede bajar más de 30% el número de productos, etc.
4. Hace commit y push; GitHub Pages lo publica en 1 o 2 minutos.

Si algo falla, se conserva el `catalogo.json` anterior y `estado.json` queda con `"resultado": "error"`; la página lo muestra en naranja.
Si el robot deja de correr más de 60 horas, la página también avisa.

## Por qué LISTA VET y no la lista maestra
El conector de Microsoft 365 solo lee archivos de hasta 100 MB. La lista maestra (`Lista Precios Hergom Vet - 2026.xlsx`, sitio kelly) pesa
más de 127 MB por las imágenes y el conector no la puede abrir; comprimir las imágenes no la bajó de peso.
`LISTA VET.xlsx` es una copia ligera, sin imágenes, solo con las columnas CLAVE, DESCRIPCIÓN, MARCA, CATEGORÍA, SUB CATEGORÍA, NOTAS, PD y PP.
El robot solo es tan fresco como esa lista: si nadie la actualiza, el resultado es "sin cambios".
Si algún día LISTA VET pasara de 100 MB, el robot lo reporta en `estado.json` y la página lo muestra.

## Cosas que cuida el script
- Tolera erratas en los encabezados (por ejemplo "CATERGORÍA GENERAL").
- Si una clave aparece repetida, gana la primera fila y queda un aviso en `estado.json` (conviene unificarlas en la hoja).
- Si falta PD o PP en una fila, publica el producto con aviso (revisa la celda). Si dice "¡Próximamente!" o "Cotizable" en lugar de precio, lo omite.
- Una fila TOTAL (suma de precios) no es obligatoria con la lectura directa; solo se exige cuando el texto se copia a mano.

## Archivos
- `catalogo.json`: productos (clave, descripción, marca, categoría, precio público con IVA `pp`, precio distribuidor sin IVA `pd`, y `nota` si la hoja la trae) y la fecha de la lista (`actualizado`).
- `estado.json`: última revisión, resultado (`ok`, `sin_cambios`, `error`), mensaje, cambios (nuevos, quitados, precios, textos) y avisos (por ejemplo, claves repetidas o precios faltantes).
- `tools/construir_catalogo.py`: convierte y verifica. Con `--prueba` escribe archivos `*-prueba.json` sin tocar los reales (bórralos después).

Las fotos no viajan en el catálogo automático: siguen incrustadas en `index.html` por clave (un producto nuevo sale con un ícono hasta que se agregue su foto).
