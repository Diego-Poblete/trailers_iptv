# Índice diario de tráilers

Este directorio se publica **solo** en un repositorio GitHub independiente. Nunca subas las carpetas `APP LG` o `APP Roku`, ni archivos `config.local.*`, paquetes IPK/ZIP, listas M3U o respuestas completas del proveedor.

## Preparación

1. Crea un repositorio nuevo para este directorio y sube **su contenido** a la rama principal.
2. En GitHub, abre **Settings → Secrets and variables → Actions** y crea `IPTV_SERVER`, `IPTV_USERNAME`, `IPTV_PASSWORD`. `TMDB_BEARER` es opcional para encontrar tráilers faltantes. Ingresa los valores solo en GitHub; no los pongas en archivos ni mensajes.
3. En **Settings → Pages → Build and deployment**, selecciona **GitHub Actions**.
4. En **Actions → Update trailer index → Run workflow**, ejecútalo una vez. Después se ejecuta diariamente a las 06:17 UTC. La hora exacta puede variar por la cola de GitHub Actions.
5. Comprueba `https://Diego-Poblete.github.io/trailers_iptv/trailers.json`. LG y Roku ya apuntan a esta URL pública. Si cambias de repositorio, ajusta `APP LG/trailer-feed.js` y `APP Roku/source/Config.brs`.

El trabajo revisa hasta 250 títulos por ejecución, empezando por los incorporados más recientemente. Conserva el avance entre ejecuciones; por eso un catálogo grande tarda varios días en completarse. Revisa de nuevo los títulos sin tráiler cada 14 días y los que tienen tráiler cada 30 días. Un tráiler ausente nunca bloquea la reproducción.

Si el proveedor falla, el workflow publica el último índice válido y termina marcado como fallido para que puedas detectar el problema. En la primera ejecución, ese índice puede estar vacío.

El JSON publicado contiene solo los títulos con tráiler: identificadores del catálogo, identificadores de YouTube y origen. El estado de revisión de los títulos sin tráiler se conserva aparte y no se descarga en las TVs. **El repositorio y el sitio son públicos**, así que no agregues nombres de usuario, URLs del proveedor ni datos privados a esos archivos. En una cuenta comercial, consulta las condiciones de uso de metadatos de TMDB y da la atribución requerida.

La app LG puede abrir el enlace oficial de YouTube desde la ficha. La reproducción en webOS 4 depende de las capacidades del navegador instalado y necesita prueba en la TV. Roku no puede prometer abrir la app de YouTube desde una aplicación propia; el índice permite mostrar la disponibilidad del tráiler, pero la reproducción dentro de Roku requiere una fuente directa autorizada por el proveedor.
