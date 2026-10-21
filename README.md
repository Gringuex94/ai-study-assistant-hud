# AI Study Assistant HUD

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-1f6aa5)
![Multithreading](https://img.shields.io/badge/Concurrencia-threading-6c757d)
![Vision LLM](https://img.shields.io/badge/Vision%20LLM-Gemini%20API-4285F4?logo=google&logoColor=white)
![MSS](https://img.shields.io/badge/Captura-MSS-2e7d32)
![License](https://img.shields.io/badge/Licencia-Todos%20los%20derechos%20reservados-red)

> Ventana flotante para Windows que mira un cuestionario de opción múltiple en tu pantalla y te marca la opción correcta con un botón.

**[Visita guiada del proyecto](https://gringuex94.github.io/ai-study-assistant-hud/)**: qué es, cómo se usa y cómo está hecho.

<!-- Cuando tengas una captura o un GIF, guardalo en assets/ y descomentá la línea de abajo -->
<!-- ![Demo](assets/demo.gif) -->

## ¿Qué problema resuelve?

Al practicar con cuestionarios online o simulacros de autoevaluación, comprobar cada respuesta obliga a salir del ejercicio, buscar y volver. Este asistente deja el cuestionario en la mitad izquierda de la pantalla y muestra el resultado en una ventana flotante a la derecha, para recibir feedback inmediato sin romper la concentración.

## Uso responsable

Está pensado para **estudiar y practicar** (quizzes, simulacros, autoevaluación). No está pensado para usarse en evaluaciones donde la ayuda externa esté prohibida.

## Cómo se usa

| Botón | Qué hace |
|---|---|
| **Inicio** | Modo rápido: captura la zona elegida y muestra la opción de cada pregunta visible (`1→B  2→C`) |
| **Avanzado** | Usa modelos más capaces con más razonamiento (acotado). Es más lento; si no está disponible, usa Inicio |
| **Ver explicación** | Muestra u oculta la explicación (solo se genera si la pedís) |

Un selector permite elegir la **zona de captura**: mitad izquierda (por defecto) o pantalla completa. En pantalla completa la ventana se vuelve transparente un instante para no aparecer en la imagen. También funcionan los atajos `F8` (Inicio), `F10` (Avanzado) y `F9` (explicación).

Cada captura queda en el historial; al tocar una vuelve a mostrarse su resultado.

## Cómo funciona

```text
Botón/atajo  ──> Captura (mss) ──> JPEG en memoria (BytesIO) ──> API de visión (Gemini)
                                                                        │
Ventana HUD (CustomTkinter) <── Parseo de la respuesta (regex) <────────┘
```

## Aspectos técnicos destacados

- **Multihilo:** la consulta a la nube corre en un hilo aparte y la interfaz se actualiza de forma segura desde el hilo principal (`after`), así la ventana no se congela mientras la IA procesa.
- **Captura sin interferencias:** en pantalla completa la ventana se vuelve transparente un instante, para no salir en la imagen que se envía.
- **Todo en RAM:** la captura se comprime a JPEG con `BytesIO`, sin escribir archivos temporales en disco.
- **Resiliencia ante la API:** si un modelo responde 503 o 429, pasa de inmediato al siguiente y lo deja en pausa 5 minutos. Recuerda qué combinación de modelo y configuración funcionó para usarla primero.
- **Velocidad vs. precisión:** el modo rápido reduce el razonamiento del modelo; el modo cuidadoso lo amplía.
- **Explicación bajo demanda:** la justificación se pide en una segunda consulta reutilizando la imagen guardada, para que el modo rápido genere menos texto.
- **Credenciales fuera del código:** la clave se lee de un archivo `.env` que no se versiona.

## Instalación

Requiere Windows y Python. Probado en Windows 11 con Python 3.14.

```powershell
git clone https://github.com/Gringuex94/ai-study-assistant-hud.git
cd ai-study-assistant-hud
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

## Configuración

1. Creá una clave en [Google AI Studio](https://aistudio.google.com/).
2. Abrí `.env` y reemplazá `tu_clave_aqui` por tu clave (sin comillas).
3. Ejecutá `python asistente.py`, poné el cuestionario en pantalla y tocá **Inicio**.

Los nombres de los modelos están en la lista `MODELS` de `asistente.py`; si Google retira alguno, se reemplaza ahí.

## Privacidad y seguridad

- La zona de pantalla elegida (por defecto, la mitad izquierda) se **envía a la API de Gemini**. La opción **Pantalla completa** envía todo lo que se vea en el monitor principal (pestañas, notificaciones, mensajes): usala solo cuando haga falta. No captures información personal o sensible. En el nivel gratuito, Google puede usar el contenido enviado para mejorar sus productos (revisá los términos vigentes).
- La clave de API vive en `.env`, que está en `.gitignore`. Si una clave se filtra, borrala en AI Studio y creá otra.
- La librería `keyboard` escucha teclas a nivel global. Esta app solo registra tres atajos (`F8`, `F9`, `F10`) y no guarda lo que escribís.

## Limitaciones

- Solo Windows (atajos globales con `keyboard`). Captura el monitor principal.
- Las respuestas pueden ser incorrectas: verificalas siempre, sobre todo con el modo rápido.
- La velocidad depende de la demanda de la API; en el nivel gratuito se observaron entre 6 y 20 segundos.
- Si las opciones no tienen letra en pantalla, el programa las asigna A, B, C, D por orden de lectura.

## Próximos pasos

- Elegir la región a capturar con el mouse.
- Tests del parser de respuestas.
- Empaquetar como `.exe`.
- Exportar el historial para repasar.

## Licencia

Todos los derechos reservados. El código se publica con fines de portafolio y evaluación: podés leerlo y ejecutarlo localmente para probarlo. Para copiarlo, modificarlo, distribuirlo o usarlo comercialmente se necesita permiso escrito del autor. Ver [LICENSE](LICENSE).

Si te interesa colaborar o tenés una propuesta, escribime.
