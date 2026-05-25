import tkinter as tk
import logging
import threading
import time
from tkinter import ttk


class MainWindow:
    def __init__(self, root: tk.Tk, app_context) -> None:
        self.root = root
        self.app_context = app_context
        self.logger = logging.getLogger(__name__)

        self._configure_root()
        self._build_layout()

    def _configure_root(self) -> None:
        self.root.title(self.app_context.settings.APP_NAME)
        self.root.minsize(1100, 700)
        self._set_window_icon_if_available()

    def _set_window_icon_if_available(self) -> None:
        icon_path = self.app_context.icons_dir / "prom9_desktop.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except Exception:
                pass

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        self._build_sidebar(container)
        self._build_main_area(container)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.Frame(parent, padding=(0, 0, 12, 0), width=240)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        ttk.Label(sidebar, text="Sesiones", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Button(sidebar, text="Nueva sesión", command=self._new_session).pack(fill=tk.X, pady=(8, 8))

        self.session_listbox = tk.Listbox(sidebar, height=20)
        self.session_listbox.pack(fill=tk.BOTH, expand=True)
        self.session_listbox.insert(tk.END, "Sesión 1")

    def _build_main_area(self, parent: ttk.Frame) -> None:
        main = ttk.Frame(parent)
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        self._build_top_bar(main)
        self._build_conversation_area(main)
        self._build_input_bar(main)

    def _build_top_bar(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, padding=(0, 0, 0, 8))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text=self.app_context.settings.APP_NAME, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        model_var = tk.StringVar(value=self.app_context.settings.DEFAULT_MODEL)
        self.model_selector = ttk.Combobox(top, textvariable=model_var, values=["gpt-4.1-mini", "gpt-4.1"], state="readonly", width=18)
        self.model_selector.grid(row=0, column=1, sticky="e")

    def _build_conversation_area(self, parent: ttk.Frame) -> None:
        conversation_frame = ttk.Frame(parent)
        conversation_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        conversation_frame.rowconfigure(0, weight=1)
        conversation_frame.columnconfigure(0, weight=1)

        self.conversation_text = tk.Text(conversation_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.conversation_text.grid(row=0, column=0, sticky="nsew")

        conversation_scrollbar = ttk.Scrollbar(
            conversation_frame, orient=tk.VERTICAL, command=self.conversation_text.yview
        )
        conversation_scrollbar.grid(row=0, column=1, sticky="ns")
        self.conversation_text.configure(yscrollcommand=conversation_scrollbar.set)

    def _build_input_bar(self, parent: ttk.Frame) -> None:
        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self.input_text = tk.Text(bottom, height=4, wrap=tk.WORD)
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input_text.bind("<Control-Return>", self._on_ctrl_enter)

        self.send_button = ttk.Button(bottom, text="Enviar", command=self._on_send)
        self.send_button.grid(row=0, column=1, sticky="ns")

    def _new_session(self) -> None:
        session_count = self.session_listbox.size() + 1
        self.session_listbox.insert(tk.END, f"Sesión {session_count}")
        self.logger.info("Nueva sesión iniciada: Sesión %s", session_count)
        self.append_system_message("Nueva sesión creada.")

    def _on_ctrl_enter(self, event: tk.Event) -> str:
        self._on_send()
        return "break"

    def _on_send(self) -> None:
        user_message = self.input_text.get("1.0", tk.END).strip()
        if not user_message:
            return

        self.logger.info("Mensaje enviado por el usuario.")
        self.append_user_message(user_message)
        self.input_text.delete("1.0", tk.END)
        self.send_button.configure(state=tk.DISABLED)

        worker = threading.Thread(
            target=self._simulate_assistant_response_worker,
            daemon=True,
        )
        worker.start()

    def _simulate_assistant_response_worker(self) -> None:
        try:
            time.sleep(0.5)
            response = "Respuesta simulada. La integración OpenAI se añadirá en una fase posterior."
            self.root.after(0, lambda: self._on_worker_success(response))
        except Exception as exc:
            self.logger.exception("Error en worker simulado: %s", exc)
            self.root.after(0, self._on_worker_error)

    def _on_worker_success(self, response: str) -> None:
        self.append_assistant_message(response)
        self.send_button.configure(state=tk.NORMAL)

    def _on_worker_error(self) -> None:
        self.append_system_message("Ocurrió un error al generar la respuesta simulada.")
        self.send_button.configure(state=tk.NORMAL)

    def append_message(self, role: str, content: str) -> None:
        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.insert(tk.END, f"{role}\n{content}\n\n")
        self.conversation_text.see(tk.END)
        self.conversation_text.configure(state=tk.DISABLED)

    def append_system_message(self, content: str) -> None:
        self.append_message("[Sistema]", content)

    def append_user_message(self, content: str) -> None:
        self.append_message("[Tú]", content)

    def append_assistant_message(self, content: str) -> None:
        self.append_message("[PROM-9]", content)
