# Actualización automática de la lista de precios

El cotizador (`index.html`) abre primero `catalogo.json` y `estado.json`, que viven junto a la página.
Un robot (tarea programada de Claude, ver `PROMPT_ROBOT.md`) los mantiene al día. Corre una vez al día, de lunes a sábado a las 6:47 p.m. (hora de Ciudad de México), después de que se actualiza la lista:

1. Lee `LISTA VET (conectada).xlsx` (OneDrive de ventasvet; desde el 2026-11-23, antes leía `LISTA VET.xlsx`, que ya no se actualiza)
   con el conector de Microsoft 365 de la cuenta de Karen (no se usa Power Automate, ni Azure, ni nada que requiera permisos de TI).
   No se fía de la fecha de modificación que da el buscador de SharePoint, porque puede ir horas atrasada: siempre lee el archivo.
2. Compara contra lo ya publicado. Si no hay diferencias, no vuelve a publicar la lista y solo actualiza `estado.json` (la fecha de la última revisión).
3. `python3 tools/construir_catalogo.py construir ...` convierte el texto en `catalogo.json` y solo lo publica si pasa las verificaciones:
   debe traer todas las filas que declara el conector, encontrar el encabezado, no puede bajar más de 30% el número de productos, etc.
4. Hace commit y push; GitHub Pages lo publica en 1 o 2 minutos.

Si algo falla, se conserva el `catalogo.json` anterior y `estado.json` queda con `"resultado": "error"`; la página lo muestra en naranja.
Si el robot deja de correr más de 60 horas, la página también avisa.

## Si la lista llega en línea y sin fila TOTAL
Según la sesión, el conector entrega la hoja guardada en un archivo (`--json`, el script la lee directo y comprueba las filas) o pegada en el texto (`--tsv`, el robot la copia a mano a /tmp/lista.txt).
El viernes 20 y el sábado 21 de noviembre el robot recibió la lista en línea, sin fila TOTAL, y no publicó nada (error "lista no verificable").
Desde el 2026-11-23 la copia a mano sin fila TOTAL se verifica contra lo ya publicado: cualquier dígito o letra mal copiada aparece como una diferencia, así que el script imprime las diferencias (NUEVO, PRECIO, TEXTO, QUITADO) y sale con código 3; el robot las compara una por una con la lectura original y repite con `--diferencias-verificadas`. Si no hay diferencias, se acepta sola. Si hay más de 12, no se puede revisar a mano: se registra un error y hace falta una fila TOTAL en la lista (suma de PD y PP). Una fila TOTAL sigue siendo la mejor verificación.
Si la hoja ya no trae las columnas de categoría o notas, el script conserva las que ya estaban publicadas (y para claves nuevas usa el último encabezado de sección, por ejemplo "RAYOS X").

## Por qué LISTA VET y no la lista maestra
El conector de Microsoft 365 solo lee archivos de hasta 100 MB. La lista maestra (`Lista Precios Hergom Vet - 2026.xlsx`, sitio kelly) pesa
más de 127 MB por las imágenes y el conector no la puede abrir; comprimir las imágenes no la bajó de peso.
`LISTA VET (conectada).xlsx` es una copia ligera, sin imágenes, con una sola hoja de datos y las columnas CLAVE, DESCRIPCIÓN, MARCA, PD y PP (la categoría y las notas ya publicadas se conservan; si la hoja vuelve a traer esas columnas, se usan).
Los precios pueden venir sin formato de moneda y con coma decimal (`1574213,103`); el script los entiende. Si un precio cambia 10 veces o más frente a lo publicado, el script no publica y lo reporta como error (casi seguro es un error de lectura de números).
El robot solo es tan fresco como esa lista: si nadie la actualiza, el resultado es "sin cambios".
Si algún día LISTA VET pasara de 100 MB, el robot lo reporta en `estado.json` y la página lo muestra.

## Cosas que cuida el script
- Tolera erratas en los encabezados (por ejemplo "CATERGORÍA GENERAL").
- Si una clave aparece repetida, gana la primera fila y queda un aviso en `estado.json` (conviene unificarlas en la hoja).
- Si falta PD o PP en una fila, publica el producto con aviso (revisa la celda). Si dice "¡Próximamente!" o "Cotizable" en lugar de precio, lo omite.
- Una fila TOTAL (suma de precios) no es obligatoria con la lectura directa; solo se exige cuando el texto se copia a mano.

## Excepciones (tools/excepciones.json)
Archivo que el robot solo lee (no lo modifica). Sirve para casos que la lista no resuelve por sí sola:
- `precios`: precio de respaldo para una clave, que se usa SOLO si la celda de la lista no trae un número (por ejemplo, si trae un punto). Si la lista vuelve a traer el número, manda la lista y `estado.json` avisa que la excepción ya se puede quitar. Hoy: V-3CFL30V con PP $2,645 (pedido de Karen, 2026-11-20).
- `cotizables`: claves que se publican sin precio, marcadas `"cotizable": true`, aunque la lista diga "¡Próximamente!" o "Cotizable". En la página salen con la leyenda "Cotizable" y el vendedor captura el precio en la partida. Hoy: MAESTRO-ELITE. Los demás productos con "Próximamente" o "COTIZABLE" (VETUSE5ADV, VETUSE3-1S, VeLED-E3M, y las 5 resonancias O-SCAN-VET, G-SCAN-EQUINE, GRANDE-ELITE-VET, MAGINIFICO-VET y SUPREME-VET) no se publican.

## Archivos
- `catalogo.json`: productos (clave, descripción, marca, categoría, precio público con IVA `pp`, precio distribuidor sin IVA `pd`, y `nota` si la hoja la trae) y la fecha de la lista (`actualizado`). Los productos cotizables llevan `"cotizable": true` y precios en 0.
- `estado.json`: última revisión, resultado (`ok`, `sin_cambios`, `error`), mensaje, cambios (nuevos, quitados, precios, textos) y avisos (por ejemplo, claves repetidas o precios faltantes).
- `tools/construir_catalogo.py`: convierte y verifica. Con `--prueba` escribe archivos `*-prueba.json` sin tocar los reales (bórralos después).

Las fotos no viajan en el catálogo automático: siguen incrustadas en `index.html` por clave (un producto nuevo sale con un ícono hasta que se agregue su foto).

## Fotos de la tienda (desde 2026-11-24)
Para productos que no tienen foto incrustada (productos libres fuera de catálogo, o claves nuevas) el cotizador busca la foto en la tienda de la empresa por clave/SKU.
- `fotos-web.json`: tabla clave -> foto. La arma `tools/fotos_tienda.py` leyendo `https://hergom-medical.com/products.json` (la tienda es Shopify y publica el SKU de cada variante y las URLs de sus fotos). Pesa unos KB: la página solo guarda la tabla y la foto se pide a la tienda al momento (con `?width=220`, para no bajar la imagen original). Sirve igual con una lista maestra de miles de claves.
- Orden de foto en el cotizador: foto incrustada en `index.html` -> foto del catálogo -> foto de la tienda -> ícono gris. Si la foto de la tienda no carga (sin internet), queda el ícono gris, nunca una imagen rota.
- `python3 tools/fotos_tienda.py` actualiza `fotos-web.json` solo si algo cambió. Si la tienda falla, responde vacía o trae menos de la mitad de las claves anteriores, NO toca el archivo y sale con error. Con `--desde archivo.json` se prueba sin leer la tienda.
- Quién lo corre cada noche: pendiente de decidir con Karen (tarea de GitHub Actions o el robot del catálogo). Desde el entorno de Claude no se alcanza hergom-medical.com (red restringida), por eso no se puede correr aquí.
- El `fotos-web.json` publicado el 2026-11-24 es una semilla de 6 claves (H2-127, 7-93-7, 7-94-7, 7-95-7, MT1 y UMEC100H) para probar de inmediato.
- Ojo: la primera foto de una variante no siempre es una foto limpia (algunas son diseños con texto). Para una clave del catálogo, la foto incrustada en `index.html` siempre gana.

## Listas de precios de productos fuera del catálogo (desde 2026-11-24)
Karen manda listas en Excel de productos que no están en LISTA VET (la primera: `LP HANDY PD PP - Mayo 2026.xlsx`, 223 claves de HANDY y YUWELL). Al escribir la clave en una partida libre, el cotizador llena marca, descripción y precio (PD y PP) con `lista-libre.json`.
- Convertir una lista: `python3 tools/construir_lista_libre.py ARCHIVO.xlsx --fuente "LP HANDY Mayo 2026"`. La hoja necesita encabezados CLAVE, NOMBRE (o DESCRIPCIÓN), MARCA, PD y PP (cualquier orden; sobran columnas como IMAGEN o EAN; las filas de sección sin clave se saltan). Quita espacios y saltos de línea de la clave, pasa clave y marca a mayúsculas, redondea precios a centavos y avisa de claves repetidas con precios distintos, precios faltantes, PP menor que PD y PP mayor a 3 veces PD.
- El nombre de `--fuente` identifica la lista: si se vuelve a correr con el mismo nombre, esa lista se reemplaza completa (una versión nueva no deja claves viejas); con otro nombre se suma, y si una clave sale en las dos gana la nueva. El resultado se sube a `lista-libre.json` (formato `{productos: {CLAVE: [marca, descripción, pd, pp, fuente]}}`).
- Prioridad al llenar una partida libre: la lista de precios (marca, descripción, precios) manda sobre la tienda (`fotos-web.json`, que aporta la foto y sirve de respaldo para marca y descripción). Una clave que está en el catálogo de Vet no se mezcla con ninguna de las dos.
- `lista-libre.json` no lo toca ningún robot: solo cambia cuando alguien corre el script y publica el resultado.
- Listas cargadas hasta ahora: `LP HANDY Mayo 2026` (223 claves) y `LP INSTRUMENTAL 2026` (1,971 claves, archivo LP_INSTRUMENTAL_2026_02_03_26_2.xlsx, dos hojas: INSTRUMENTAL y ACERO INOXIDABLE). Con las dos, `lista-libre.json` pesa unos 270 KB (unos 41 KB al descargarse comprimido) y se baja al abrir la página; si algún día una lista pesa decenas de miles de claves conviene cargarla solo cuando se necesite.
- Hojas sin encabezado en las columnas de precio (ACERO INOXIDABLE): el script toma las dos columnas siguientes a la última con título como PD y PP y avisa para que se confirme. Las filas sin ningún precio (títulos repetidos como "ARTICULO") se saltan.

