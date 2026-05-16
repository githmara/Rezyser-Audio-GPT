¡Hola! Gracias por el reporte detallado — dos respuestas precisas:

**1. „Abrir ubicación del archivo" (sin „la") es la forma correcta y es exactamente lo que dice el manual.**

Acabo de revisar `docs/manual.es.txt` de v15.2.5 — la opción aparece sin „la" en las cuatro menciones (paso 2 de la migración, consejo para usuarios de NVDA, sección de actualizaciones automáticas y el consejo final). Incluso hay una nota explícita en el manual:

> Consejo: „Abrir ubicación del archivo" es el nombre nativo de la opción en una versión española de Windows (Microsoft usa esta forma sin „la" tanto en español de España como en variantes latinoamericanas).

Es muy posible que tu lector haya inferido el „la" gramaticalmente al pasar rápido por el párrafo — es un fenómeno común al leer en español. Estás en el menú correcto, no te equivocaste.

**2. Es un comportamiento esperado de la migración 15.2.3 → 15.2.5, no un problema de tu sistema. El manual lo describe explícitamente.**

En v15.2.4 y anteriores, la aplicación se distribuía como Portable ZIP y se iniciaba mediante `run.bat`. En v15.2.5 abandonamos por completo el paquete ZIP — ahora hay un único modo de despliegue: el instalador `.exe`, que crea su propio ejecutable independiente. Tu acceso directo del escritorio se quedó apuntando a la ruta antigua de v15.2.3 (`...\run.bat`), que ya no existe después del upgrade.

El manual v15.2.5 tiene un párrafo dedicado a este escenario, en la sección „Actualizaciones automáticas":

> Aviso al actualizar desde versiones anteriores (v15.2.4 o más antigua, cuando la aplicación se iniciaba mediante `run.bat` del paquete Portable ZIP): tu acceso directo del escritorio puede apuntar a `run.bat` en la ubicación antigua, que ya no existe después de actualizar a v15.2.5+ — las versiones 15.2.5+ usan un archivo `.exe` independiente creado por el instalador. Si tu acceso directo deja de funcionar después de la actualización, bórralo manualmente y deja que el instalador cree uno nuevo en la siguiente instalación.

**Procedimiento concreto para tu caso:**

1. Borra el acceso directo viejo del escritorio (el que apunta a `run.bat`).
2. Comprueba primero el Menú Inicio: pulsa la tecla Windows, escribe „Director de Audio" — si aparece, NVDA lo leerá y podrás abrirlo con Enter. El instalador de v15.2.5 normalmente crea ese acceso del Menú Inicio automáticamente.
3. Si quieres recuperar también el acceso directo del escritorio: vuelve a ejecutar el instalador de v15.2.5 (no es necesario desinstalar primero — sobrescribe la instalación existente sin tocar tus proyectos ni `golden_key.env`). En el asistente, marca la casilla „Crear un acceso directo en el escritorio" si la opción aparece. Importante: asegúrate de que la ruta de instalación propuesta coincide con la que usaste originalmente; si no, obtendrás una segunda instalación vacía — el manual lo advierte en el mismo párrafo.
4. Alternativa manual: navega con el Explorador a la carpeta donde instalaste v15.2.5, localiza el `.exe` principal, pulsa la tecla Aplicación → „Enviar a" → „Escritorio (crear acceso directo)". NVDA lee toda esta secuencia de menús sin problemas.

Avísame si después del paso 3 sigues sin tener un acceso directo funcional — en ese caso pásame la ruta exacta donde instalaste v15.2.5 y depuramos juntos.
