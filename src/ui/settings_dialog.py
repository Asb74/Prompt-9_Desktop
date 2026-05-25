import logging
import os
import tkinter as tk
from tkinter import messagebox, ttk

from src.config import local_config, settings


class SettingsDialog(tk.Toplevel):
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
        self.streaming_var = tk.BooleanVar(value=bool(current["streaming_enabled"]))

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
        self.max_spin = ttk.Spinbox(frame, from_=1, to=100, textvariable=self.max_context_var, width=8)
        self.max_spin.grid(row=2, column=1, sticky="w", pady=(8, 8))

        self.streaming_check = ttk.Checkbutton(frame, text="Streaming habilitado", variable=self.streaming_var)
        self.streaming_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))

        api_key_detected = bool((os.environ.get("OPENAI_API_KEY") or "").strip())
        api_key_text = "API key detectada" if api_key_detected else "API key no detectada"
        ttk.Label(frame, text=f"Estado OpenAI: {api_key_text}").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="La API key debe configurarse en .env (OPENAI_API_KEY).", foreground="#666666").grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.logger.info("Estado API key al abrir configuración: %s", api_key_text)

        btns = ttk.Frame(frame)
        btns.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Guardar", command=self._save).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side=tk.LEFT)

    def _validated_payload(self) -> dict[str, object] | None:
        model = settings.normalize_model(self.default_model_var.get())
        prompt = self.prompt_text.get("1.0", tk.END).strip() or settings.SYSTEM_PROMPT

        raw_ctx = self.max_context_var.get().strip()
        try:
            max_ctx = int(raw_ctx)
        except ValueError:
            messagebox.showerror("Configuración", "'Máx. mensajes contexto' debe ser un entero positivo.", parent=self)
            return None

        if max_ctx <= 0:
            messagebox.showerror("Configuración", "'Máx. mensajes contexto' debe ser mayor que cero.", parent=self)
            return None

        return {
            "default_model": model,
            "system_prompt": prompt,
            "max_context_messages": max_ctx,
            "streaming_enabled": bool(self.streaming_var.get()),
        }

    def _save(self) -> None:
        payload = self._validated_payload()
        if payload is None:
            return

        local_config.save_local_config(payload)
        settings.LOCAL_CONFIG = local_config.load_local_config(settings)
        self.logger.info("Configuración guardada desde diálogo de ajustes.")
        self.on_save_callback(payload)
        self.destroy()
