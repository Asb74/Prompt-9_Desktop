import logging
import re
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.config.settings import normalize_model
from src.managers.chat_manager import ChatManager
from src.managers.session_storage import SessionStorage
from src.services.export_service import ExportService
from src.ui.settings_window import SettingsWindow


class MainWindow:
    ROLE_DISPLAY = {"system": "Sistema", "user": "Tú", "assistant": "PROM-9"}

    def __init__(self, root: tk.Tk, app_context) -> None:
        self.root = root
        self.app_context = app_context
        self.logger = logging.getLogger(__name__)

        self.chat_manager = ChatManager()
        self.session_storage = SessionStorage()
        self.export_service = ExportService()

        self.sessions_by_id: dict[str, dict] = {}
        self.session_order: list[str] = []
        self.current_session_id: str | None = None
        self.partial_message_start_index: str | None = None

        self._configure_root()
        self._build_layout()
        self._load_initial_sessions()

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
        ttk.Button(sidebar, text="Nueva sesión", command=self._new_session).pack(fill=tk.X, pady=(8, 6))
        ttk.Button(sidebar, text="Renombrar", command=self._rename_session).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(sidebar, text="Eliminar", command=self._delete_session).pack(fill=tk.X, pady=(0, 8))

        self.session_listbox = tk.Listbox(sidebar, height=20)
        self.session_listbox.pack(fill=tk.BOTH, expand=True)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)

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

        ttk.Label(top, text=self.app_context.settings.APP_NAME, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")

        default_model = normalize_model(self.app_context.settings.DEFAULT_MODEL)
        self.model_selector = ttk.Combobox(
            top,
            textvariable=tk.StringVar(value=default_model),
            values=self.app_context.settings.AVAILABLE_MODELS,
            state="readonly",
            width=18,
        )
        self.model_selector.grid(row=0, column=1, sticky="e")
        self.model_selector.set(default_model)
        ttk.Button(top, text="Exportar", command=self._export_current_session).grid(row=0, column=2, padx=(8, 0), sticky="e")
        ttk.Button(top, text="Configuración", command=self._open_settings_window).grid(row=0, column=3, padx=(8, 0), sticky="e")


    def _export_current_session(self) -> None:
        if not self.current_session_id:
            messagebox.showwarning("Exportar", "No hay una sesión activa para exportar.", parent=self.root)
            return

        session = self.sessions_by_id.get(self.current_session_id)
        if not session:
            messagebox.showwarning("Exportar", "No hay una sesión activa para exportar.", parent=self.root)
            return

        output_path = filedialog.asksaveasfilename(
            title="Exportar conversación",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Markdown", "*.md")],
            parent=self.root,
        )
        if not output_path:
            return

        self.logger.info("Exportación iniciada: sesión=%s destino=%s", self.current_session_id, output_path)
        if output_path.lower().endswith(".md"):
            ok = self.export_service.export_session_to_markdown(session, output_path)
        else:
            ok = self.export_service.export_session_to_txt(session, output_path)

        if ok:
            self.logger.info("Exportación completada: sesión=%s destino=%s", self.current_session_id, output_path)
            messagebox.showinfo("Exportar", "Conversación exportada correctamente.", parent=self.root)
            return

        self.logger.error("Error exportando sesión=%s destino=%s", self.current_session_id, output_path)
        messagebox.showerror("Exportar", "No se pudo exportar la conversación.", parent=self.root)

    def _open_settings_window(self) -> None:
        SettingsWindow(self.root, self._on_settings_saved)

    def _on_settings_saved(self, payload: dict[str, object]) -> None:
        model = normalize_model(str(payload.get("default_model", "")))
        self.model_selector.configure(values=self.app_context.settings.AVAILABLE_MODELS)
        self.model_selector.set(model)
        self.chat_manager.update_runtime_settings(
            system_prompt=str(payload.get("system_prompt", self.app_context.settings.SYSTEM_PROMPT)),
            max_context_messages=int(payload.get("max_context_messages", self.app_context.settings.MAX_CONTEXT_MESSAGES)),
            api_key=self.app_context.settings.resolve_api_key(str(payload.get("openai_api_key", ""))),
        )
        self.logger.info("Configuración actualizada desde ventana de ajustes.")

    def _build_conversation_area(self, parent: ttk.Frame) -> None:
        conversation_frame = ttk.Frame(parent)
        conversation_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        conversation_frame.rowconfigure(0, weight=1)
        conversation_frame.columnconfigure(0, weight=1)

        self.conversation_text = tk.Text(conversation_frame, wrap=tk.WORD, state=tk.DISABLED, padx=12, pady=10, spacing1=2, spacing3=8)
        self.conversation_text.grid(row=0, column=0, sticky="nsew")
        self.conversation_text.tag_configure("header_user", foreground="#1d4ed8", font=("Segoe UI", 10, "bold"))
        self.conversation_text.tag_configure("header_assistant", foreground="#047857", font=("Segoe UI", 10, "bold"))
        self.conversation_text.tag_configure("header_system", foreground="#7c3aed", font=("Segoe UI", 10, "bold"))
        self.conversation_text.tag_configure("body", font=("Segoe UI", 10), lmargin1=4, lmargin2=4, spacing3=12)

        conversation_scrollbar = ttk.Scrollbar(conversation_frame, orient=tk.VERTICAL, command=self.conversation_text.yview)
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

    def _load_initial_sessions(self) -> None:
        sessions = self.session_storage.list_sessions()
        for session in sessions:
            self._cache_session(session)

        if not self.session_order:
            self.logger.info("No había sesiones; se crea una nueva.")
            self._new_session()
            return

        self._refresh_session_listbox()
        self._select_session(self.session_order[0])

    def _new_session(self) -> None:
        self._save_current_session_if_needed()
        selected_model = normalize_model(self.model_selector.get())
        session = self.session_storage.create_session(model=selected_model)
        self.session_storage.save_session(session)
        self._cache_session(session, prepend=True)
        self._refresh_session_listbox()
        self._select_session(session["id"])

    def _rename_session(self) -> None:
        if not self.current_session_id:
            return
        current_title = self.sessions_by_id[self.current_session_id].get("title", "")
        new_title = simpledialog.askstring("Renombrar sesión", "Nuevo nombre:", initialvalue=current_title, parent=self.root)
        if not new_title or not new_title.strip():
            return
        updated = self.session_storage.rename_session(self.current_session_id, new_title)
        if not updated:
            return
        self.sessions_by_id[self.current_session_id] = updated
        self._refresh_session_listbox()
        self._select_session(self.current_session_id)

    def _delete_session(self) -> None:
        if not self.current_session_id:
            return
        session_id = self.current_session_id
        title = self.sessions_by_id[session_id].get("title", "Nueva sesión")
        if not messagebox.askyesno("Eliminar sesión", f"¿Eliminar la sesión '{title}'?", parent=self.root):
            return

        self.session_storage.delete_session(session_id)
        self.sessions_by_id.pop(session_id, None)
        if session_id in self.session_order:
            self.session_order.remove(session_id)
        self.current_session_id = None
        self._refresh_session_listbox()

        if self.session_order:
            self._select_session(self.session_order[0])
        else:
            self._new_session()

    def _cache_session(self, session: dict, prepend: bool = False) -> None:
        session_id = session["id"]
        self.sessions_by_id[session_id] = session
        if session_id in self.session_order:
            self.session_order.remove(session_id)
        if prepend:
            self.session_order.insert(0, session_id)
        else:
            self.session_order.append(session_id)

    def _refresh_session_listbox(self) -> None:
        self.session_listbox.delete(0, tk.END)
        for session_id in self.session_order:
            title = self.sessions_by_id[session_id].get("title", "Nueva sesión")
            self.session_listbox.insert(tk.END, title)

    def _select_session(self, session_id: str) -> None:
        loaded_session = self.session_storage.load_session(session_id) or self.sessions_by_id.get(session_id)
        if not loaded_session:
            return
        self.sessions_by_id[session_id] = loaded_session
        self.current_session_id = session_id

        index = self.session_order.index(session_id)
        self.session_listbox.selection_clear(0, tk.END)
        self.session_listbox.selection_set(index)
        self.session_listbox.activate(index)

        session_model = normalize_model(loaded_session.get("model"))
        loaded_session["model"] = session_model
        self.model_selector.set(session_model)

        self.chat_manager.conversation_manager.load_messages(loaded_session.get("messages", []))
        self._clear_conversation_view()
        for msg in loaded_session.get("messages", []):
            self.append_message(msg.get("role", "system"), msg.get("content", ""), msg.get("created_at"))
        self.logger.info("Sesión seleccionada: %s", session_id)

    def _on_session_select(self, event: tk.Event) -> None:
        if not self.session_listbox.curselection():
            return
        index = self.session_listbox.curselection()[0]
        session_id = self.session_order[index]
        if session_id != self.current_session_id:
            self._save_current_session_if_needed()
            self._select_session(session_id)

    def _save_current_session_if_needed(self) -> None:
        if not self.current_session_id:
            return
        session = self.sessions_by_id.get(self.current_session_id)
        if not session:
            return
        session["model"] = normalize_model(self.model_selector.get())
        self.session_storage.save_session(session)

    def _on_ctrl_enter(self, event: tk.Event) -> str:
        self._on_send()
        return "break"

    def _on_send(self) -> None:
        user_message = self.input_text.get("1.0", tk.END).strip()
        if not user_message or not self.current_session_id:
            return

        self.append_user_message(user_message)
        self._store_message("user", user_message)
        self.input_text.delete("1.0", tk.END)
        self.send_button.configure(state=tk.DISABLED)

        model = normalize_model(self.model_selector.get())
        self.model_selector.set(model)
        self.sessions_by_id[self.current_session_id]["model"] = model
        worker = threading.Thread(target=self._assistant_response_worker, args=(user_message, model), daemon=True)
        worker.start()

    def _assistant_response_worker(self, user_message: str, model: str) -> None:
        try:
            response = self.chat_manager.send_message(user_message, model)
            self.root.after(0, lambda: self._on_worker_success(response))
        except Exception:
            self.logger.exception("Error en worker de asistencia")
            self.root.after(0, self._on_worker_error)

    def _on_worker_success(self, response: str) -> None:
        if response:
            self.append_assistant_message(response)
            self._store_message("assistant", response)
        self.send_button.configure(state=tk.NORMAL)

    def _on_worker_error(self) -> None:
        error_msg = "No se pudo obtener respuesta de OpenAI. Revisa la configuración, el modelo o la conexión."
        self.append_system_message(error_msg)
        self.send_button.configure(state=tk.NORMAL)

    def _store_message(self, role: str, content: str) -> None:
        if not self.current_session_id or not content.strip():
            return
        session = self.sessions_by_id[self.current_session_id]
        msg = {"role": role, "content": content, "created_at": datetime.now(timezone.utc).isoformat()}
        session.setdefault("messages", []).append(msg)
        self.session_storage.update_session_title_from_first_user_message(session)
        self._refresh_session_listbox()
        self.session_storage.save_session(session)

    def _clear_conversation_view(self) -> None:
        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.delete("1.0", tk.END)
        self.conversation_text.configure(state=tk.DISABLED)

    def _clean_markdown_basic(self, content: str) -> str:
        lines = content.splitlines()
        cleaned_lines: list[str] = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                cleaned_lines.append(line)
                continue
            if not in_code_block:
                line = re.sub(r"^\s{0,3}#{1,3}\s*", "", line)
                line = line.replace("**", "")
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def _format_timestamp(self, created_at: str | None) -> str:
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                return dt.strftime("%H:%M")
            except ValueError:
                pass
        return datetime.now().strftime("%H:%M")

    def append_message(self, role: str, content: str, created_at: str | None = None) -> None:
        role_key = role if role in self.ROLE_DISPLAY else "system"
        label = self.ROLE_DISPLAY.get(role_key, "Sistema")
        tag = f"header_{role_key}"
        timestamp = self._format_timestamp(created_at)
        cleaned_content = self._clean_markdown_basic(content)

        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.insert(tk.END, f"[{timestamp}] {label}\n", tag)
        self.conversation_text.insert(tk.END, f"{cleaned_content}\n\n", "body")
        self.conversation_text.see(tk.END)
        self.conversation_text.configure(state=tk.DISABLED)

    def append_system_message(self, content: str) -> None:
        self.append_message("system", content)

    def append_user_message(self, content: str) -> None:
        self.append_message("user", content)

    def append_assistant_message(self, content: str) -> None:
        self.append_message("assistant", content)

    def append_partial_message(self, role: str, partial_content: str) -> None:
        """Prepara el área de chat para streaming incremental futuro sin activarlo aún."""
        if self.partial_message_start_index is None:
            self.partial_message_start_index = self.conversation_text.index(tk.END)
            self.append_message(role, partial_content)
            return

        # Mantiene compatibilidad actual: sustituye el último bloque parcial completo.
        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.delete(self.partial_message_start_index, tk.END)
        self.conversation_text.configure(state=tk.DISABLED)
        self.append_message(role, partial_content)

    def finish_partial_message(self) -> None:
        """Finaliza un mensaje parcial para futuras respuestas con streaming real."""
        self.partial_message_start_index = None

