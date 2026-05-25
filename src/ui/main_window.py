import tkinter as tk
from tkinter import ttk


class MainWindow:
    def __init__(self, root: tk.Tk, app_context) -> None:
        self.root = root
        self.app_context = app_context

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
        self.conversation_text = tk.Text(parent, wrap=tk.WORD, state=tk.DISABLED)
        self.conversation_text.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

    def _build_input_bar(self, parent: ttk.Frame) -> None:
        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self.input_text = tk.Text(bottom, height=4, wrap=tk.WORD)
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        send_button = ttk.Button(bottom, text="Enviar", command=self._on_send)
        send_button.grid(row=0, column=1, sticky="ns")

    def _new_session(self) -> None:
        session_count = self.session_listbox.size() + 1
        self.session_listbox.insert(tk.END, f"Sesión {session_count}")
        self._append_message("Sistema", "Nueva sesión creada.")

    def _on_send(self) -> None:
        user_message = self.input_text.get("1.0", tk.END).strip()
        if not user_message:
            return

        self.input_text.delete("1.0", tk.END)
        self._append_message("Usuario", user_message)
        self._append_message(
            "PROM-9",
            "Respuesta simulada. La integración OpenAI se añadirá en una fase posterior.",
        )

    def _append_message(self, sender: str, message: str) -> None:
        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.insert(tk.END, f"{sender}:\n{message}\n\n")
        self.conversation_text.see(tk.END)
        self.conversation_text.configure(state=tk.DISABLED)
