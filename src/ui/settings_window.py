import logging
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from src.config import local_config, settings
from src.services.openai_client import OpenAIClient


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, on_save_callback) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.on_save_callback = on_save_callback
        self.title("Configuración")
        self.transient(parent)
        self.resizable(True, True)
        self.grab_set()

        current = settings.effective_settings()
        self.default_model_var = tk.StringVar(value=str(current["default_model"]))
        self.max_context_var = tk.StringVar(value=str(current["max_context_messages"]))
        self.api_key_var = tk.StringVar(value=str(settings.LOCAL_CONFIG.get("openai_api_key", "")))
        self._show_api_key = False

        self._build_ui(str(current["system_prompt"]))

    def _build_ui(self, system_prompt: str) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Modelo por defecto").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.model_combo = ttk.Combobox(frame, values=settings.AVAILABLE_MODELS, textvariable=self.default_model_var, state="readonly")
        self.model_combo.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Prompt de sistema").grid(row=1, column=0, sticky="nw")
        self.prompt_text = tk.Text(frame, height=8, wrap=tk.WORD)
        self.prompt_text.grid(row=1, column=1, sticky="nsew")
        self.prompt_text.insert("1.0", system_prompt)

        ttk.Label(frame, text="Máx. mensajes contexto").grid(row=2, column=0, sticky="w", pady=(8, 8))
        self.max_spin = ttk.Spinbox(frame, from_=4, to=100, textvariable=self.max_context_var, width=8)
        self.max_spin.grid(row=2, column=1, sticky="w", pady=(8, 8))

        ttk.Label(frame, text="API key OpenAI").grid(row=3, column=0, sticky="w")
        key_frame = ttk.Frame(frame)
        key_frame.grid(row=3, column=1, sticky="ew")
        key_frame.columnconfigure(0, weight=1)
        self.api_key_entry = ttk.Entry(key_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(key_frame, text="Mostrar/Ocultar", command=self._toggle_api_key).grid(row=0, column=1, padx=4)
        ttk.Button(key_frame, text="Limpiar", command=lambda: self.api_key_var.set("")).grid(row=0, column=2)

        btns = ttk.Frame(frame)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Probar conexión OpenAI", command=self._test_connection).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Guardar", command=self._save).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT)

    def _toggle_api_key(self) -> None:
        self._show_api_key = not self._show_api_key
        self.api_key_entry.configure(show="" if self._show_api_key else "*")

    def _validated_payload(self) -> dict[str, object]:
        model = settings.normalize_model(self.default_model_var.get())
        prompt = self.prompt_text.get("1.0", tk.END).strip() or settings.SYSTEM_PROMPT
        try:
            max_ctx = int(self.max_context_var.get().strip())
        except ValueError:
            max_ctx = settings.MAX_CONTEXT_MESSAGES
        max_ctx = max(4, min(100, max_ctx))
        api_key = self.api_key_var.get().strip()
        return {
            "default_model": model,
            "system_prompt": prompt,
            "max_context_messages": max_ctx,
            "openai_api_key": api_key,
        }

    def _save(self) -> None:
        payload = self._validated_payload()
        local_config.save_local_config(payload)
        settings.LOCAL_CONFIG = local_config.load_local_config(settings)
        self.logger.info("API key configurada: %s", "sí" if bool(payload["openai_api_key"]) else "no")
        self.on_save_callback(payload)
        self.destroy()

    def _test_connection(self) -> None:
        payload = self._validated_payload()
        api_key = settings.resolve_api_key(str(payload["openai_api_key"]))
        model = str(payload["default_model"])

        def worker() -> None:
            try:
                client = OpenAIClient(api_key=api_key)
                if not client.is_configured():
                    raise RuntimeError("API key no configurada")
                reply = client.generate_text(
                    messages=[{"role": "user", "content": "Responde solo: OK"}],
                    model=model,
                )
                ok = "OK" in (reply or "")
                self.after(0, lambda: messagebox.showinfo("OpenAI", "Conexión OpenAI correcta." if ok else "Conexión OpenAI correcta."))
            except Exception:
                self.logger.exception("Fallo en prueba de conexión OpenAI")
                self.after(0, lambda: messagebox.showerror("OpenAI", "No se pudo conectar con OpenAI. Revisa la clave, el modelo o la conexión."))

        threading.Thread(target=worker, daemon=True).start()
