# ZonaProp: cómo obtener la cookie `cf_clearance`

ZonaProp está protegido por **Cloudflare**. Para scrapearlo sin abrir ventana (headless),
el programa reusa una cookie **`cf_clearance`** que vos generás resolviendo el desafío de
Cloudflare una vez en tu navegador. Esa cookie está atada a tu **User-Agent**, tu **IP** y
el **fingerprint TLS** del navegador, así que hay que respetar tres cosas (ver más abajo).

> ArgenProp **no** necesita nada de esto: va directo por HTTP.

## Paso a paso (repetible)

1. Abrí **Brave/Chrome** y entrá a una URL de listado, por ejemplo:
   `https://www.zonaprop.com.ar/departamentos-alquiler-belgrano.html`
2. Si aparece el desafío de Cloudflare ("Un momento…" / verificación), esperá/resolvelo
   hasta ver los departamentos.
3. Apretá **F12** → pestaña **Application** (en español "Aplicación"; si no la ves, está
   detrás del botón **`»`**).
4. Menú izquierdo: **Cookies** → `https://www.zonaprop.com.ar`.
5. En la tabla, buscá la fila **Name = `cf_clearance`**.
6. **Doble clic en su valor** (columna Value, un texto largo) → **Ctrl+C**.
7. En el programa: panel **Scraping** → marcá **ZonaProp** → pegá el valor en
   **"Cookie ZonaProp (`cf_clearance`)"** → **Iniciar Scraping**.

Eso es todo. La próxima vez repetís los pasos 1–7 (solo cambia el valor de la cookie).

## Importante

- **La cookie vence** (horas). Si ZonaProp empieza a fallar o trae 0 resultados, volvé a
  sacar una `cf_clearance` fresca y pegala de nuevo.
- **Mismo navegador siempre.** El programa manda un User-Agent fijo
  (`ZONAPROP_USER_AGENT`) y un perfil TLS (`ZONAPROP_IMPERSONATE`). El default está seteado
  para **Brave/Chrome 149 en Windows**. Si usás otro navegador o versión, actualizá esas dos
  variables en `.env` (ver `ZONAPROP_*` abajo) para que coincidan con el navegador donde
  sacás la cookie — si no coinciden, Cloudflare rechaza la cookie.
- **Misma IP.** La cookie sirve desde la misma IP donde la generaste. Corriendo local
  (tu PC) se cumple solo. Si el scraper corre en un servidor con otra IP, la cookie de tu
  casa probablemente no sirva.
- **Volumen.** Cloudflare puede volver a desafiar tras muchas páginas; si pasa, el run corta
  esa parte y conviene refrescar la cookie.

## Variables de entorno (`.env`)

```
# Navegador con el que generás la cookie cf_clearance (deben coincidir UA + impersonate)
ZONAPROP_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36
ZONAPROP_IMPERSONATE=chrome146
```

`ZONAPROP_IMPERSONATE` es el perfil de TLS de `scrapling`/`curl_cffi` más cercano a tu
navegador (ej. `chrome146`, `chrome131`, `firefox144`). Elegí el más alto que sea ≤ a tu
versión de Chrome.
