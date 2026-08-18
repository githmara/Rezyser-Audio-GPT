# Reżyser Audio GPT

**Estudio de Grabación Híbrido para Dramas de Audio, Audiolibros y Narraciones Interactivas**

**Otras versiones lingüísticas / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Conjunto de herramientas autocontenidas impulsadas por IA para la escritura automática, planificación, formato y traducción de guiones extensos, así como para la ejecución de juegos de texto interactivos. El proyecto es una aplicación de escritorio nativa (wxPython) diseñada desde cero con plena accesibilidad para lectores de pantalla (NVDA, VoiceOver) y compatibilidad con sintetizadores de voz profesionales (TTS). Funciona sin navegador y sin servidor local: se ejecuta como una ventana de programa normal.

Versión: **18.21.0** · Idiomas soportados de forma nativa (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Módulos principales

La aplicación combina en una sola ventana cinco herramientas que se pueden alternar mediante atajos de teclado (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) o botones en la barra de herramientas. Cada módulo funciona de manera independiente, pero todos comparten paquetes de diccionarios del directorio `dictionaries/` (acentos, cifrados, modos creativos de IA) y configuraciones centrales.


### 1. Dirección (Ctrl+1)

El estudio principal para escribir radioteatros y audiolibros. Eliges el modo — Lluvia de Ideas, Guion (con etiquetas `[SFX]`/`[Personaje: emoción]`), Audiolibro (prosa tradicional) — y diriges el diálogo con el modelo a través del campo de Instrucciones + Libro del Mundo + Memoria a Largo Plazo:

* **Libro del Mundo Multiproyecto:** El sistema carga automáticamente en segundo plano las reglas dedicadas del universo (`.md`) basándose en el archivo fuente activo, asegurando un aislamiento completo (carga de contexto sin clics).
* **Acumulador de Trama:** Algoritmo de "memoria infinita". El resumen de la trama lo genera una herramienta de postproducción aparte (desde v18.13) y, cuando el indicador de memoria entra en estado de alerta roja, el sistema la ejecuta por su cuenta y guarda el resultado tanto en el archivo como en el campo de Memoria a Largo Plazo. Los resúmenes sucesivos son incrementales: el modelo recibe la memoria anterior y solo la parte nueva de la narración.
* **6 modos creativos:** Cada uno de los archivos en `dictionaries/<jzk>/rezyser/` describe una "personalidad" separada del director de IA (Lluvia de Ideas, Guion, Audiolibro) o una herramienta de postproducción (Títulos de Capítulos, Memoria a Largo Plazo). Puedes ajustar su tono sin programación — ver Gestor de Reglas más abajo.


### 2. Historias (Ctrl+5, segundo modo principal desde v15.0)

Juegos de texto interactivos dirigidos por la IA en el papel de motor narrativo. A diferencia de la Dirección (donde generas un audiolibro terminado), Historias es una trama dinámica turno por turno:

* **Modo Elecciones:** cada turno termina con 3-5 opciones numeradas A-E. El modo más intuitivo para jugadores invidentes — NVDA lee las opciones, pulsas Tab e Intro.
* **Modo Mal Menor:** como Elecciones, pero cada opción es desfavorable moral, física o estratégicamente. Desde v15.2 se añade una «ampolla» adicional — una opción reutilizable numerada como CERO de rescate desesperado, cuyos efectos son pseudoaleatorios (60% perjudiciales / 30% que alteran la percepción / 10% raramente favorables, distribución forzada por Python, el LLM no tiene forma de inventar un resultado salvador).
* **Modo Libre:** cualquier acción en texto libre («intentaré abrir la puerta»), el motor propone 1-3 sugerencias pero no impone una elección.
* **Un solo modelo de IA para todos los modos:** desde v18.1 todos los modos de Historias utilizan el mismo modelo compartido (por defecto y recomendado Anthropic Claude Sonnet 5) — un modelo más potente se atiene rigurosamente a las reglas del mundo (clave especialmente en el modo Mal Menor, donde cada opción debe ser realmente desfavorable).


### 3. Políglota (Ctrl+2, Traductor IA + Acentos TTS)

* **Traductor Seguro:** Los textos largos se dividen automáticamente en bloques medidos en tokens del modelo (seguro también para idiomas de escritura densa, p. ej. el chino) y se traducen secuencialmente; una respuesta cortada del modelo se detecta y se reintenta en fragmentos más pequeños. Cada bloque se guarda inmediatamente en un archivo `.jsonl` oculto. La reanudación después de alcanzar los límites de la API es completamente automática.
* **Automatización NVDA:** Las traducciones se guardan como archivos `.html` listos con la etiqueta de idioma incorporada o archivos `.docx` con etiquetas inyectadas directamente en la estructura XML.
* **8 acentos locales:** Posibilidad de forzar intencionadamente un acento roto para los sintetizadores locales (Tiflotecnia Voices, eSpeak, OneCore) mediante reglas avanzadas de regex. Acentos extranjeros soportados: inglés, ruso (con transliteración al cirílico), francés, alemán, polaco, italiano, finlandés, islandés.
* **Modo Cifrador:** 6 algoritmos locales que distorsionan el texto, desde la lectura al revés, pasando por tipoglicemia, hasta el clásico cifrado César. Cada uno con el alfabeto local del paquete de idioma (por ejemplo, cifrado César en un alfabeto PL de 35 caracteres con diacríticos).
* **Reparador de Etiquetas:** Inyecta de manera no invasiva el código de idioma ISO proporcionado — también regional, p. ej. pt-BR o zh-CN — en archivos existentes.


### 4. Convertidor / Arquitecto de Audiolibros (Ctrl+3)

* Procesa archivos `.txt` o `.docx` en bruto para navegación por teclado para NVDA y sistemas como ElevenLabs.
* Convierte automáticamente palabras clave (Acto, Capítulo, Prólogo) en encabezados "Heading 1" en un documento de Word, y también limpia etiquetas HTML innecesarias y marcadores Markdown.
* Desde la versión v15.1, agrupa 5 turnos en escenas con encabezados H1 (detección automática de Historias) — prepara el archivo generado por el modo Historia para la publicación tradicional de audiolibros.


### 5. Gestor de Reglas (Ctrl+4, novedad desde v13.0)

* **Explorador de diccionarios sin Python:** Árbol visual de todos los archivos YAML en la carpeta `dictionaries/` — acentos fonéticos, cifrados, modos creativos del Director y Narrador. Un lingüista o traductor puede explorar, duplicar, editar y eliminar reglas directamente desde la interfaz gráfica.
* **Creador de nuevas reglas:** Formulario con selección de tipo (acento, cifrado de sustitución simple, modo del Director, nuevo idioma base, cifrado algorítmico) que crea una plantilla YAML lista, y para casos más complejos, genera un prompt formateado para pegar en ChatGPT / Claude.
* **Refactorización v13.0 — reglas en YAML:** Todos los acentos, cifrados y modos de IA, que hasta la versión 12.0 existían como constantes "embebidas" en el código Python, han sido trasladados a archivos `.yaml` declarativos que se cargan dinámicamente al iniciar la aplicación. Cualquiera que pueda manejar el Bloc de notas puede ajustar un acento (por ejemplo, cambiar `sz → sh` a `sz → sch`), añadir un nuevo idioma, e incluso cambiar el tono del prompt del sistema para la IA, sin compilar el código.


## Multilingüismo (9 idiomas nativos)

Desde la versión v14.0, la aplicación admite de forma nativa 9 idiomas base: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Cada paquete `dictionaries/<kod>/` contiene diacríticos, alfabeto y reglas fonéticas que operan en el texto en ese idioma específico: la aplicación detecta automáticamente el idioma de origen a través de lingua-language-detector (por párrafo) y carga el paquete adecuado para cada fragmento por separado.

Toda la interfaz GUI, la documentación (`docs/manual.<iso>.html`) y la mayoría de los mensajes del sistema están disponibles de forma nativa en cada uno de los idiomas compatibles. Los mensajes del sistema de IA en los modos Director y Narrativa están escritos en los idiomas de destino (manualmente, no autotraducidos — ver `dictionaries/<kod>/rezyser/` y `dictionaries/<kod>/opowiesci/`).


## Arquitectura de IA y modelos utilizados

El proveedor de IA recomendado y predeterminado es Anthropic (Claude) — todos los prompts del sistema están ajustados para él, por lo que es el que ofrece la más alta calidad narrativa, el mejor cumplimiento de las reglas del mundo y la prosa más natural. La consolidación en Claude se llevó a cabo por etapas (Director en v18.0, Historias en v18.1, Políglota y postproducción en v18.2) — resultado de una ventaja empíricamente confirmada en el cumplimiento de las reglas del mundo, la naturalidad de la prosa y la evitación de clichés.

* **Anthropic Claude Sonnet 5 (pilar predeterminado de calidad):** Motor de TODA la inteligencia de la aplicación. Se encarga de la narración creativa (dirección de guiones, redacción de la prosa tradicional del Audiolibro, la Lluvia de Ideas y TODOS los modos de Historias — Elecciones, El Mal Menor, Libre — junto con la generación de resúmenes e interludios Cinematic), traducciones avanzadas con preservación del contexto multibloque (Políglota), así como microtareas: la asignación iterativa de títulos literarios a los capítulos y la detección del código de idioma del contenido.

* **Endpoint propio compatible con OpenAI (opción avanzada, desde v18.4):** En lugar de Anthropic se puede indicar cualquier endpoint compatible con la API de OpenAI (OpenRouter, Groq, Fireworks, DeepSeek, Ollama local, Gemini compatible con OpenAI y otros) — mediante una única ruta de código compartida, sin necesidad de una integración separada por proveedor. Configuración en el archivo `golden_key.env` (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY`); instrucciones completas en el manual principal (PASO 2B). Otros modelos pueden ofrecer una calidad inferior a Claude, para el cual están ajustados los prompts — es una elección consciente de coste↔calidad por parte del usuario.


### Limitaciones conocidas de los modelos (Anti-Closure)

A pesar de la implementación de directrices sistemáticas rigurosas que ordenan cortar la acción en momentos de tensión (la llamada directriz Anti-Closure), los modelos LLM modernos tienen una fuerte tendencia innata a "cerrar" las historias. Esto resulta en la frecuente inclusión de conclusiones no deseadas, moralejas o falsos "finales felices", especialmente en el Modo de Audiolibro Tradicional.

Esta es una limitación fundamental de la generación actual de inteligencia artificial. Por esta razón, la aplicación guarda los proyectos en archivos de texto simples y fáciles de editar (`.txt`). Esto requiere que el usuario asuma el papel de un editor humano, eliminando manualmente las últimas oraciones "cerradoras" generadas por la IA, y luego sincronizando la memoria con el archivo corregido mediante el botón "Actualizar desde disco", y continuando trabajando.


## Instalación y puesta en marcha

### Para usuarios finales (Windows)

1. Descarga la versión más reciente desde la pestaña **Releases** (el paquete marcado como *Latest*) — archivo `Rezyser_Audio_v<numer>_Installer.exe`. Ejecútalo con doble clic. El instalador se ubica por defecto en el directorio local de tu cuenta (`%LocalAppData%\Programs\Reżyser Audio GPT`) y no requiere permisos de administrador; puedes elegir tu propia ruta con el botón «Examinar». Al finalizar, crea accesos directos en el Menú Inicio y en el escritorio, y opcionalmente abre el manual de usuario en el editor predeterminado de archivos `.txt`.
2. **Configuración de la API de Anthropic:** En el primer arranque, la aplicación indicará la ausencia de clave en la sección System Check. Haz clic en el botón visible para generar el archivo `golden_key.env`, ábrelo en un editor de texto e introduce tu clave de Anthropic (que comienza por `sk-ant-`).
3. **Primeros pasos:** Abre el archivo `docs/manual.pl.html` (o en otro idioma) en la carpeta de instalación — es el manual de usuario completo, escrito en un lenguaje accesible para cualquier usuario, no solo para desarrolladores.


### Para desarrolladores (clonar + configurar)

1. Clona el repositorio en tu disco.
2. Ejecuta el archivo `setup_dev.bat` para crear automáticamente un entorno virtual (`.venv/`) y descargar las dependencias desde `requirements.txt`.
3. Ejecuta la aplicación con el comando `python main.py` o mediante el archivo `run_dev.bat`.

Los scripts `.sh` para macOS/Linux fueron eliminados en la versión v13.1 — el entorno de desarrollo está centrado en Windows debido a la especificidad de las pruebas de accesibilidad de NVDA. Trabajar con el código en otros sistemas es posible, pero requiere configuración manual: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Scripts para construir paquetes de lanzamiento** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) se utilizan exclusivamente para crear paquetes para Windows. Desde la versión 17.0, `build_release.py` congela la aplicación con PyInstaller (onedir + windowed) según `rezyser_audio.spec` — produce `dist/` con un `.exe` nativo y una carpeta de bundle `runtime/` (intérprete + bibliotecas). Ya no es necesario ningún Python portátil cargado manualmente en el repositorio; los directorios `dist/` y `build/` están en `.gitignore`.


## Documentación completa

Este README es solo un esquema arquitectónico del proyecto. Para conocer las técnicas avanzadas de prevención de alucinaciones de IA, las instrucciones de instalación de sintetizadores de voz compatibles (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), la descripción completa de los modos de Historias con ampolla, y la guía completa del usuario, consulta los archivos en la carpeta `docs/`:

* `docs/manual.<iso>.html` — manual principal de usuario (escrito para el usuario final).
* `docs/tales.<iso>.html` — manual del modo Historias (juegos de texto interactivos).
* `docs/dictionaries.<iso>.html` — instrucciones para lingüistas sin Python sobre cómo añadir sus propios acentos/códigos/modos de IA.

Cada uno de estos archivos está disponible en 9 idiomas — sufijo `.<iso>.html` (por ejemplo, `manual.pl.html`, `manual.en.html`, `manual.de.html`).


### Guía de nombres polacos — para personas fuera del ámbito lingüístico polaco

El idioma principal de este proyecto es el polaco. Los nombres de los módulos, clases, comentarios en el código, así como los nombres de directorios y archivos de datos están en polaco y — debido a la compatibilidad retroactiva y al contrato del motor multilingüe — deliberadamente NO se traducen ni cambian. El siguiente glosario ayudará a los desarrolladores y usuarios de sistemas macOS/Linux a orientarse en la estructura.

**Directorios de datos del usuario (junto al archivo ejecutable o en el directorio del proyecto):**

* `skrypty/` — *scripts*: proyectos del módulo Director (`.txt` con la narración, `.md` con el Libro del Mundo, `_streszczenie.txt`).
* `opowiesci/` — *stories*: registros de Historias interactivas.
* `runtime/` — doble función: directorio del paquete de la aplicación congelada (intérprete + bibliotecas) Y contenedor de metadatos ocultos de los proyectos (`runtime/skrypty/`, `runtime/opowiesci/`).

**Subcarpetas de datos fuente en `dictionaries/<código-idioma>/` (visibles en el Gestor de Reglas):**

* `podstawy.yaml` — *basics*: configuración y metadatos del paquete de idioma.
* `akcenty/` — *accents*: reglas fonéticas para los sintetizadores de voz.
* `szyfry/` — *ciphers*: modos de cifrado de texto.
* `rezyser/` — *director*: modos creativos del módulo Director.
* `opowiesci/` — *stories*: modos de Historias interactivas.
* `gui/` — textos de la interfaz (`ui.yaml`) y plantillas de documentación.


## Licencia

El proyecto se distribuye bajo la licencia **MIT** — el texto completo se encuentra en el archivo [`LICENSE`](LICENSE) en el directorio principal del repositorio. En resumen: puedes usar, copiar, modificar y distribuir el software libremente (incluso comercialmente), siempre que mantengas la nota de derechos de autor. El software se proporciona "tal cual", sin ninguna garantía.
