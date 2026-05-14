# Director de Audio GPT

**Estudio de Grabación Híbrido para Dramas de Audio, Audiolibros y Narraciones Interactivas**

**Otras versiones lingüísticas / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Conjunto de herramientas portátiles impulsadas por IA para la escritura automática, planificación, formato y traducción de guiones extensos, así como para la ejecución de juegos de texto interactivos. El proyecto es una aplicación de escritorio nativa (wxPython) diseñada desde cero con plena accesibilidad para lectores de pantalla (NVDA, VoiceOver) y compatibilidad con sintetizadores de voz profesionales (TTS). Funciona sin navegador y sin servidor local: se ejecuta como una ventana de programa normal.

Versión: **15.1** · Idiomas soportados de forma nativa (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Módulos principales

La aplicación combina en una sola ventana cinco herramientas que se pueden alternar mediante atajos de teclado (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) o botones en la barra de herramientas. Cada módulo funciona de manera independiente, pero todos comparten paquetes de diccionarios del directorio `dictionaries/` (acentos, cifrados, modos creativos de IA) y configuraciones centrales.


### 1. Dirección (Ctrl+1)

El estudio principal para escribir radioteatros y audiolibros. Eliges el modo — Lluvia de Ideas, Guion (con etiquetas `[SFX]`/`[Personaje: emoción]`), Audiolibro (prosa tradicional) — y diriges el diálogo con el modelo a través del campo de Instrucciones + Libro del Mundo + Memoria a Largo Plazo:

* **Libro del Mundo Multiproyecto:** El sistema carga automáticamente en segundo plano las reglas dedicadas del universo (`.md`) basándose en el archivo fuente activo, asegurando un aislamiento completo (carga de contexto sin clics).
* **Acumulador de Trama:** Algoritmo de "memoria infinita". Cuando el indicador de memoria entra en estado de alerta roja, el sistema genera automáticamente un resumen de la trama y lo guarda en el campo de Memoria a Largo Plazo.
* **4 modos creativos:** Cada uno de los archivos en `dictionaries/<jzk>/director/` describe una "personalidad" separada del director de IA (Lluvia de Ideas, Guion, Audiolibro, Postproducción de Títulos). Puedes ajustar su tono sin programación — ver Administrador de Reglas más abajo.


### 2. Historias (Ctrl+2, segundo modo principal desde v15.0)

Juegos de texto interactivos dirigidos por IA como motor narrativo. A diferencia de la Dirección (donde generas un audiolibro completo), Historias es una narrativa dinámica turno por turno:

* **Modo Elecciones:** cada turno termina con 3-5 opciones numeradas A-E. El modo más intuitivo para jugadores ciegos: NVDA lee las opciones, haces clic en Tab y Enter.
* **Modo Menor Mal:** como Elecciones, pero cada opción es moralmente, físicamente o estratégicamente desfavorable. Desde v15.2 un "frasco" adicional: opción de rescate desesperado numerada CERO reutilizable, cuyos efectos son pseudoaleatorios (60% perjudicial / 30% alteración de la percepción / 10% raramente beneficioso, distribución forzada por Python, LLM no puede inventar un resultado salvador).
* **Modo Libre:** cualquier acción con texto libre ("intentaré abrir la puerta"), el motor propone 1-3 sugerencias pero no impone una elección.
* **Modelo AI por modo:** Elecciones y Menor Mal usan gpt-4o (mejor razonamiento moral), Libre usa gpt-4o-mini (economía de improvisación más barata).


### 3. Políglota (Ctrl+3, Traductor AI + Acentos TTS)

* **Traductor Seguro:** Los textos largos se dividen automáticamente en bloques de hasta 10,000 caracteres y se traducen secuencialmente. Cada bloque se guarda inmediatamente en un archivo `.jsonl` oculto. La reanudación después de alcanzar los límites de la API es completamente automática.
* **Automatización NVDA:** Las traducciones se guardan como archivos `.html` listos con la etiqueta de idioma incorporada o archivos `.docx` con etiquetas inyectadas directamente en la estructura XML.
* **8 acentos locales:** Posibilidad de forzar intencionadamente un acento roto para los sintetizadores locales (Tiflotecnia Voices, eSpeak, OneCore) mediante reglas avanzadas de regex. Acentos extranjeros soportados: inglés, ruso (con transliteración al cirílico), francés, alemán, español, italiano, finlandés, islandés.
* **Modo Cifrador:** 6 algoritmos locales que distorsionan el texto, desde la lectura al revés, pasando por tipoglicemia, hasta el clásico cifrado César. Cada uno con el alfabeto local del paquete de idioma (por ejemplo, cifrado César en un alfabeto PL de 35 caracteres con diacríticos).
* **Reparador de Etiquetas:** Inyecta de manera no invasiva el código de idioma ISO de dos letras proporcionado en archivos existentes.


### 4. Convertidor / Arquitecto de Audiolibros (Ctrl+4)

* Procesa archivos `.txt` o `.docx` en bruto para navegación por teclado para NVDA y sistemas como ElevenLabs.
* Convierte automáticamente palabras clave (Acto, Capítulo, Prólogo) en encabezados "Heading 1" en un documento de Word, y también limpia etiquetas HTML innecesarias y marcadores Markdown.
* Desde la versión v15.1, agrupa 5 turnos en escenas con encabezados H1 (detección automática de Historias) — prepara el archivo generado por el modo Historia para la publicación tradicional de audiolibros.


### 5. Gestor de Reglas (Ctrl+5, novedad desde v13.0)

* **Explorador de diccionarios sin Python:** Árbol visual de todos los archivos YAML en la carpeta `dictionaries/` — acentos fonéticos, cifrados, modos creativos del Director y Narrador. Un lingüista o traductor puede explorar, duplicar, editar y eliminar reglas directamente desde la interfaz gráfica.
* **Creador de nuevas reglas:** Formulario con selección de tipo (acento, cifrado de sustitución simple, modo del Director, nuevo idioma base, cifrado algorítmico) que crea una plantilla YAML lista, y para casos más complejos, genera un prompt formateado para pegar en ChatGPT / Claude.
* **Refactorización v13.0 — reglas en YAML:** Todos los acentos, cifrados y modos de IA, que hasta la versión 12.0 existían como constantes "embebidas" en el código Python, han sido trasladados a archivos `.yaml` declarativos que se cargan dinámicamente al iniciar la aplicación. Cualquiera que pueda manejar el Bloc de notas puede ajustar un acento (por ejemplo, cambiar `sz → sh` a `sz → sch`), añadir un nuevo idioma, e incluso cambiar el tono del prompt del sistema para la IA, sin compilar el código.


## Multilingüismo (9 idiomas nativos)

Desde la versión v14.0, la aplicación admite de forma nativa 9 idiomas base: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Cada paquete `dictionaries/<código>/` contiene diacríticos, alfabeto y reglas fonéticas que operan en el texto en ese idioma específico: la aplicación detecta automáticamente el idioma de origen a través de lingua-language-detector (por párrafo) y carga el paquete adecuado para cada fragmento por separado.

Toda la interfaz GUI, la documentación (`docs/manual.<iso>.txt`) y la mayoría de los mensajes del sistema están disponibles de forma nativa en cada uno de los idiomas compatibles. Los mensajes del sistema de IA en los modos Director y Narrativa están escritos en los idiomas de destino (manualmente, no autotraducidos — ver `dictionaries/<código>/director/` y `dictionaries/<código>/narrativa/`).


## Arquitectura de IA y modelos utilizados

La aplicación distribuye inteligentemente las tareas, optimizando los costos y la velocidad de funcionamiento del API de OpenAI:

* **gpt-4o:** El motor principal que impulsa la aplicación. Se encarga de tareas generativas pesadas: dirección de guiones, escritura de prosa tradicional (Audiolibro), modos de Elecciones y Menor de Dos Males en Historias, generación de resúmenes y traducciones avanzadas manteniendo el contexto multibloque.
* **gpt-4o-mini:** Un modelo auxiliar rápido y ligero. Se utiliza en segundo plano para microtareas que requieren alta velocidad: asignación iterativa de títulos literarios a los capítulos generados, extracción de códigos ISO, modo Libre en Historias (economía más barata de improvisación de texto libre).


### Limitaciones conocidas de los modelos (Anti-Closure)

A pesar de la implementación de directrices sistemáticas rigurosas que ordenan cortar la acción en momentos de tensión (la llamada directriz Anti-Closure), los modelos LLM modernos tienen una fuerte tendencia innata a "cerrar" las historias. Esto resulta en la frecuente inclusión de conclusiones no deseadas, moralejas o falsos "finales felices", especialmente en el Modo de Audiolibro Tradicional.

Esta es una limitación fundamental de la generación actual de inteligencia artificial. Por esta razón, la aplicación guarda los proyectos en archivos de texto simples y fáciles de editar (`.txt`). Esto requiere que el usuario asuma el papel de un editor humano, eliminando manualmente las últimas oraciones "cerradoras" generadas por la IA antes de volver a cargar el archivo y continuar trabajando.


## Instalación y ejecución

### Para usuarios finales (Windows)

1. Descarga la última versión desde la pestaña **Releases** (el paquete marcado como *Latest*). Hay dos formas disponibles:
   * **Installer EXE** — instala en Archivos de Programa (o en la carpeta seleccionada), crea accesos directos en el Menú de Inicio y en el escritorio. Al finalizar la instalación, opcionalmente abre el manual de usuario en el manejador predeterminado de .txt.
   * **Portable ZIP** — descomprime en cualquier carpeta, no requiere permisos de administrador. Después de descomprimir, ejecuta `run.bat`.
2. **Configuración del API de OpenAI:** Al primer inicio, la aplicación señalará la falta de una clave en la sección System Check. Haz clic en el botón visible para generar el archivo `golden_key.env`, ábrelo en un editor de texto y pega tu clave (que comienza con `sk-proj-`).
3. **Primeros pasos:** Abre el archivo `docs/manual.pl.txt` (o en otro idioma) en la carpeta de instalación — es un manual de usuario completo escrito en un lenguaje accesible para cualquier usuario, no solo para desarrolladores.


### Para desarrolladores (clonar + configurar)

1. Clona el repositorio en tu disco.
2. Ejecuta el archivo `setup_dev.bat` para crear automáticamente un entorno virtual (`.venv/`) y descargar las dependencias de `requirements.txt`.
3. Ejecuta la aplicación con el comando `python main.py` o a través del archivo `run_dev.bat`.

Los scripts `.sh` para macOS/Linux fueron eliminados en la versión v13.1 — el entorno de desarrollo está centrado en Windows debido a la especificidad de las pruebas de accesibilidad de NVDA. Trabajar con el código en otros sistemas es posible, pero requiere una configuración manual: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Los scripts para construir paquetes de lanzamiento** (`build_release.py`, `installer.iss`) se utilizan exclusivamente para crear paquetes para Windows. Requieren una carpeta especial `runtime/` con una versión portátil de Python — esta carpeta no es parte del repositorio intencionalmente (está en `.gitignore`).


## Documentación completa

Este README es solo un esquema arquitectónico del proyecto. Para conocer las técnicas avanzadas de prevención de alucinaciones de IA, las instrucciones de instalación de sintetizadores de voz compatibles (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), la descripción completa de los modos de Historias con frasco, y la guía completa del usuario, consulta los archivos en la carpeta `docs/`:

* `docs/manual.<iso>.txt` — manual principal de usuario (escrito para el usuario final).
* `docs/tales.<iso>.txt` — manual del modo Historias (juegos de texto interactivos).
* `docs/dictionaries.<iso>.txt` — instrucciones para lingüistas sin Python sobre cómo añadir sus propios acentos/códigos/modos de IA.

Cada uno de estos archivos está disponible en 9 idiomas — sufijo `.<iso>.txt` (por ejemplo, `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).
