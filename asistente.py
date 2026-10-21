import io
import os
import re
import time
import threading
import traceback
from pathlib import Path

import customtkinter as ctk
import keyboard
import mss
from PIL import Image
from google import genai
from google.genai import types

# ==========================================
# CONFIGURACIÓN
# ==========================================
# La clave se lee del archivo .env que está AL LADO de este archivo:
#   GEMINI_API_KEY=tu_clave
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    print("Falta python-dotenv:  python -m pip install python-dotenv")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Modelos a probar en orden (si uno da 404 o falla, pasa al siguiente).
MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-pro-preview",
]

# Primero intenta SIN "pensar" (mucho más rápido); si el modelo no lo acepta, usa la config normal.
def _cfg(**think):
    """Config con razonamiento reducido; devuelve None si el SDK no soporta ese ajuste."""
    try:
        return types.GenerateContentConfig(
            temperature=0, thinking_config=types.ThinkingConfig(**think)
        )
    except Exception:
        return None


# Gemini 3 usa "thinking_level"; Gemini 2.5 usa "thinking_budget". Se prueban en ese orden
# (un 400 es instantáneo) y al final la config normal.
CONFIGS = [c for c in (_cfg(thinking_level="MINIMAL"), _cfg(thinking_budget=0)) if c]
CONFIGS.append(types.GenerateContentConfig(temperature=0))

MAX_SIDE = 1600   # si tu pantalla es muy grande, se achica la captura (más rápido)
JPEG_QUALITY = 70

ZONE_LEFT = "Mitad izquierda"
ZONE_FULL = "Pantalla completa"

PROMPT_ANSWERS = (
    "La imagen contiene preguntas multiple choice. Resolvé TODAS las preguntas que se vean "
    "completas (enunciado y opciones) e ignorá las que estén cortadas. "
    "Respondé SOLO una línea por pregunta con el formato `NUMERO: LETRA`, usando el número "
    "que muestra la pantalla (si no hay números, usá 1, 2, 3 en orden). "
    "Si una pregunta admite varias respuestas, separá las letras con coma: `3: A,C`. "
    "Las opciones se letran A, B, C, D en orden de lectura (de arriba hacia abajo y de izquierda "
    "a derecha), aunque la pantalla no muestre la letra o la haya reemplazado por un ícono. "
    "Si la pantalla ya muestra respuestas marcadas (en rojo, verde o con tilde), no las uses "
    "como guía: resolvé vos la pregunta. "
    "Sin explicaciones ni texto extra."
)

PROMPT_EXPLAIN = (
    "Estas son las respuestas que diste a las preguntas de la imagen:\n{answers}\n\n"
    "Explicá en 1 o 2 frases por qué es correcta cada una, una línea por pregunta, "
    "con el formato `NUMERO: explicación`."
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

MSS = getattr(mss, "MSS", None) or mss.mss

# Combinación (modelo, config) que funcionó la última vez: se prueba primero
_preferred = None


COOLDOWN_S = 300      # un modelo saturado (503/429) se saltea durante 5 minutos
_cooldown = {}        # modelo -> momento hasta el que se saltea


CAREFUL_MODELS = ["gemini-flash-latest", "gemini-3.1-pro-preview"]

# Modo cuidadoso: razonamiento ACOTADO (antes era ilimitado y podía tardar minutos)
CAREFUL_CONFIGS = [c for c in (_cfg(thinking_budget=2048), _cfg(thinking_level="LOW")) if c]
CAREFUL_CONFIGS.append(types.GenerateContentConfig(temperature=0))


def make_client():
    """Cliente con tiempo máximo de espera por consulta (60 s), para no quedar colgado."""
    try:
        return genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=60_000))
    except Exception:
        return genai.Client(api_key=API_KEY)


def _cooldown_seconds(e):
    """Cuánto conviene no volver a probar un modelo después de este error."""
    code = getattr(e, "code", None)
    m = re.search(r"retryDelay\W+(\d+(?:\.\d+)?)s", str(e))
    if code == 429 and m:                  # cuota agotada: Google informa cuándo vuelve
        return min(float(m.group(1)), 12 * 3600)
    if code in (429, 500, 503, 504):       # saturación
        return COOLDOWN_S
    if code is None:                       # timeout o error de red
        return 60
    return 0                               # 400/404: no es saturación


def ask_gemini(client, contents, careful=False):
    """Devuelve (texto, modelo). Ante saturación o cuota pasa YA al siguiente modelo."""
    global _preferred
    last_error = None

    if careful:
        for model in CAREFUL_MODELS:
            # una pausa corta (saturación) se ignora acá; una larga (cuota diaria) se respeta
            if _cooldown.get(model, 0) - time.time() > COOLDOWN_S:
                continue
            for cfg in CAREFUL_CONFIGS:
                try:
                    r = client.models.generate_content(model=model, contents=contents, config=cfg)
                    return (r.text or ""), model
                except Exception as e:
                    last_error = e
                    code = getattr(e, "code", None)
                    print(f"[cuidadoso {model}] {code} {str(e)[:150]}")
                    if code == 400:
                        continue  # config no soportada por este modelo: probar la siguiente
                    secs = _cooldown_seconds(e)
                    if secs:
                        _cooldown[model] = time.time() + secs
                    break  # pasar al siguiente modelo
        print("Modo avanzado no disponible: se usa el modo Inicio")
        texto, model = ask_gemini(client, contents)
        return texto, f"{model}, avanzado no disponible"

    candidates = [(m, i) for m in MODELS for i in range(len(CONFIGS))]
    if _preferred in candidates:
        candidates.remove(_preferred)
        candidates.insert(0, _preferred)

    tried = False
    for model, cfg_i in candidates:
        if _cooldown.get(model, 0) > time.time():
            continue  # saturado o sin cuota hace poco: no perder tiempo
        tried = True
        try:
            r = client.models.generate_content(
                model=model, contents=contents, config=CONFIGS[cfg_i]
            )
            _preferred = (model, cfg_i)
            return (r.text or ""), model
        except Exception as e:
            last_error = e
            code = getattr(e, "code", None)
            print(f"[{model} cfg{cfg_i}] {code} {str(e)[:150]}")
            secs = _cooldown_seconds(e)
            if secs:
                _cooldown[model] = time.time() + secs
            # 400/404: se prueba la siguiente config o el siguiente modelo

    if not tried:  # todos estaban en pausa: limpiar y volver a intentar
        _cooldown.clear()
        return ask_gemini(client, contents)
    raise last_error or RuntimeError("Sin respuesta de ningún modelo")


def parse_answers(texto):
    """Convierte las líneas 'N: LETRA' en [(N, 'LETRA')]."""
    out = []
    for m in re.finditer(
        r"^\s*(\d+)\s*[:\-.)]\s*([A-Za-z](?:\s*,\s*[A-Za-z])*)\s*$", texto, re.MULTILINE
    ):
        out.append((m.group(1), m.group(2).upper().replace(" ", "")))
    return out


class StudyAssistantApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Study Assistant - HUD")
        self.geometry("450x650")
        self.attributes("-topmost", True)

        self.history = []          # dicts: label, answers_text, img, expl
        self.current_index = None
        self.busy = False
        self.explanation_visible = False

        self.client = make_client() if API_KEY else None

        self.lbl_status = ctk.CTkLabel(
            self, text="Elegí la zona y tocá Inicio",
            font=("Arial", 13, "italic"), wraplength=420,
        )
        self.lbl_status.pack(pady=10)

        self.btn_start = ctk.CTkButton(
            self, text="Inicio", height=64, font=("Arial", 24, "bold"),
            command=lambda: self.trigger_capture_async(False),
        )
        self.btn_start.pack(fill="x", padx=15, pady=(0, 6))

        self.btn_adv = ctk.CTkButton(
            self, text="Avanzado", height=36, font=("Arial", 14),
            fg_color="#334155", hover_color="#475569",
            command=lambda: self.trigger_capture_async(True),
        )
        self.btn_adv.pack(fill="x", padx=15, pady=(0, 6))

        self.zone_full = False
        self.seg_zone = ctk.CTkSegmentedButton(
            self, values=[ZONE_LEFT, ZONE_FULL], command=self.on_zone_change
        )
        self.seg_zone.set(ZONE_LEFT)
        self.seg_zone.pack(fill="x", padx=15, pady=(0, 6))

        self.card_current = ctk.CTkFrame(self, corner_radius=10)
        self.card_current.pack(fill="x", padx=15, pady=5)

        self.lbl_badge = ctk.CTkLabel(self.card_current, text="Esperando captura...", font=("Arial", 12))
        self.lbl_badge.pack(anchor="w", padx=15, pady=(10, 0))

        self.lbl_answer = ctk.CTkLabel(
            self.card_current, text="--", font=("Arial", 30, "bold"),
            text_color="#10b981", wraplength=400,
        )
        self.lbl_answer.pack(pady=10, padx=10)

        # La explicación está OCULTA hasta que se pide (botón o F9)
        self.btn_explain = ctk.CTkButton(
            self.card_current, text="Ver explicación",
            command=self.toggle_explanation, state="disabled",
        )
        self.btn_explain.pack(pady=(0, 12))

        self.txt_explanation = ctk.CTkTextbox(self.card_current, height=130, wrap="word")

        ctk.CTkLabel(
            self, text="Historial de capturas", font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        self.scroll_history = ctk.CTkScrollableFrame(self, height=260)
        self.scroll_history.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        keyboard.add_hotkey("f8", self.trigger_capture_async)
        keyboard.add_hotkey("f10", lambda: self.trigger_capture_async(True))
        self.after(300, self.anchor_right)
        keyboard.add_hotkey("f9", lambda: self.after(0, self.toggle_explanation))

        if not self.client:
            self.lbl_status.configure(
                text="Falta GEMINI_API_KEY en el archivo .env (y guardalo con Ctrl+S)",
                text_color="#ef4444",
            )

    # ---------- helpers thread-safe ----------
    def ui(self, fn, *args, **kwargs):
        self.after(0, lambda: fn(*args, **kwargs))

    def set_status(self, text, color):
        self.ui(self.lbl_status.configure, text=text, text_color=color)

    # ---------- captura y consulta ----------
    def anchor_right(self):
        """Ancla la ventana al borde derecho de la pantalla, a lo alto."""
        try:
            self.update_idletasks()
            w = self.winfo_width()
            h = self.winfo_screenheight() - 80
            x = self.winfo_screenwidth() - w
            self.wm_geometry(f"{w}x{h}+{x}+0")
        except Exception:
            pass

    def on_zone_change(self, value):
        self.zone_full = (value == ZONE_FULL)

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.ui(self.btn_start.configure, state=state)
        self.ui(self.btn_adv.configure, state=state)

    def trigger_capture_async(self, careful=False):
        if self.busy or not self.client:
            return
        self.set_busy(True)
        threading.Thread(target=self.process_screen, args=(careful,), daemon=True).start()

    def grab_screen(self):
        """Captura la zona elegida. En pantalla completa oculta el HUD un instante."""
        full = self.zone_full
        if full:
            done = threading.Event()

            def hide():
                self.attributes("-alpha", 0.0)
                self.update_idletasks()
                done.set()

            self.after(0, hide)
            done.wait(1)
            time.sleep(0.25)
        try:
            with MSS() as sct:
                mon = sct.monitors[1]
                region = {
                    "top": mon["top"],
                    "left": mon["left"],
                    "width": mon["width"] if full else mon["width"] // 2,
                    "height": mon["height"],
                }
                shot = sct.grab(region)
                return Image.frombytes("RGB", shot.size, shot.rgb)
        finally:
            if full:
                self.ui(self.attributes, "-alpha", 1.0)

    def process_screen(self, careful=False):
        label = "Avanzado" if careful else "Inicio"
        self.set_status(
            "Analizando a fondo (puede tardar)..." if careful else "Capturando y resolviendo...",
            "#38bdf8",
        )
        t0 = time.perf_counter()
        try:
            img = self.grab_screen()
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY)
            img_bytes = buf.getvalue()
            t_capture = time.perf_counter() - t0

            texto, model = ask_gemini(
                self.client,
                [types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), PROMPT_ANSWERS],
                careful,
            )
            total = time.perf_counter() - t0
            print(f"[{label} · {model}] captura {t_capture:.2f}s | total {total:.2f}s\n{texto}")

            answers = parse_answers(texto)
            self.ui(self.update_ui, answers, texto.strip(), img_bytes, total, f"{label} · {model}")

        except Exception as e:
            traceback.print_exc()
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                msg = "Cuota de la API agotada (nivel gratuito). Esperá o revisá tu plan en AI Studio."
            self.set_status(f"Error: {msg[:200]}", "#ef4444")
        finally:
            self.set_busy(False)

    def fetch_explanation(self, index):
        item = self.history[index]
        try:
            texto, _ = ask_gemini(
                self.client,
                [
                    types.Part.from_bytes(data=item["img"], mime_type="image/jpeg"),
                    PROMPT_EXPLAIN.format(answers=item["answers_text"]),
                ],
            )
            item["expl"] = texto.strip() or "(sin explicación)"
        except Exception as e:
            traceback.print_exc()
            item["expl"] = f"Error al explicar: {str(e)[:150]}"
        if self.current_index == index and self.explanation_visible:
            self.ui(self.set_explanation_text, item["expl"])

    # ---------- interfaz ----------
    def set_explanation_text(self, text):
        self.txt_explanation.configure(state="normal")
        self.txt_explanation.delete("1.0", "end")
        self.txt_explanation.insert("1.0", text)
        self.txt_explanation.configure(state="disabled")

    def hide_explanation(self):
        self.txt_explanation.pack_forget()
        self.explanation_visible = False
        self.btn_explain.configure(text="Ver explicación")

    def toggle_explanation(self):
        if self.current_index is None:
            return
        if self.explanation_visible:
            self.hide_explanation()
            return

        item = self.history[self.current_index]
        self.txt_explanation.pack(fill="x", padx=15, pady=(0, 15))
        self.explanation_visible = True
        self.btn_explain.configure(text="Ocultar explicación")

        if item["expl"] is None:
            self.set_explanation_text("Generando explicación...")
            threading.Thread(
                target=self.fetch_explanation, args=(self.current_index,), daemon=True
            ).start()
        else:
            self.set_explanation_text(item["expl"])

    def show_history_item(self, index):
        self.current_index = index
        item = self.history[index]
        self.lbl_badge.configure(text=f"Captura #{index + 1}")
        self.lbl_answer.configure(text=item["label"])
        self.hide_explanation()

    def update_ui(self, answers, raw, img_bytes, elapsed, model):
        if answers:
            label = "   ".join(f"{n}→{l}" for n, l in answers)
            answers_text = "\n".join(f"{n}: {l}" for n, l in answers)
            expl = None  # se pide con F9
        else:
            label = "Sin preguntas legibles"
            answers_text = raw
            expl = raw or "(sin respuesta)"  # lo que dijo el modelo, visible con F9

        self.history.append(
            {"label": label, "answers_text": answers_text, "img": img_bytes, "expl": expl}
        )
        index = len(self.history) - 1

        self.btn_explain.configure(state="normal")
        self.show_history_item(index)
        self.lbl_badge.configure(text=f"Captura #{index + 1} resuelta")

        ctk.CTkButton(
            self.scroll_history,
            text=f"Captura {index + 1}:  {label}",
            anchor="w", fg_color="transparent", border_width=1,
            command=lambda i=index: self.show_history_item(i),
        ).pack(fill="x", pady=3, padx=2)

        self.lbl_status.configure(
            text=f"Listo en {elapsed:.1f} s ({model}).",
            text_color="#10b981",
        )


if __name__ == "__main__":
    app = StudyAssistantApp()
    app.mainloop()
