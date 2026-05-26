import logging
import re
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.config.settings import normalize_model
from src.config import settings
from src.managers.chat_manager import ChatManager
from src.managers.attachment_manager import AttachmentManager
from src.database.database import Database
from src.database.json_migrator import JsonMigrator
from src.database.session_repository import SessionRepository
from src.services.text_chunker import build_document_context
from src.services.conversation_exporter import ConversationExporter
from src.ui.settings_dialog import SettingsDialog
from src.services.table_loader import TableLoader
from src.services.table_analysis_engine import TableAnalysisEngine
from src.services.semantic_column_inference import SemanticColumnInference
from src.services.tabular_intent_resolver import TabularIntentResolver


class MainWindow:
    ROLE_DISPLAY = {"system": "Sistema", "user": "Tú", "assistant": "PROM-9"}
    DOCUMENT_REFERENCE_TERMS = (
        "archivo", "documento", "adjunto", "excel", "hoja", "tabla", "datos",
        "pdf", "word", "csv", "xlsx", "variedad", "kg", "kilos",
    )
    TABULAR_RISK_TERMS = (
        "socio", "entrega", "entregas", "kilos", "kg", "neto", "importe",
        "precio", "variedad", "cultivo", "producto", "total", "resumen",
        "top", "mayor", "mas", "más",
    )

    def __init__(self, root: tk.Tk, app_context) -> None:
        self.root = root
        self.app_context = app_context
        self.logger = logging.getLogger(__name__)

        current = self.app_context.settings.effective_settings()
        self.chat_manager = ChatManager(streaming_enabled=bool(current["streaming_enabled"]))
        self.chat_manager.update_runtime_settings(
            system_prompt=str(current["system_prompt"]),
            max_context_messages=int(current["max_context_messages"]),
            streaming_enabled=bool(current["streaming_enabled"]),
            api_key=self.app_context.settings.resolve_api_key(),
        )
        self.database = Database()
        self.database.initialize()
        self.session_repository = SessionRepository(self.database)
        self.json_migrator = JsonMigrator(self.session_repository)
        self.attachment_manager = AttachmentManager(self.session_repository)
        self.pending_attachments: list[dict] = []
        self.conversation_exporter = ConversationExporter()
        self.table_loader = TableLoader()
        self.table_analysis_engine = TableAnalysisEngine()
        self.semantic_inference = SemanticColumnInference()

        self.sessions_by_id: dict[str, dict] = {}
        self.session_order: list[str] = []
        self.session_list_items: list[dict] = []
        self.current_session_id: str | None = None
        self.session_search_query = tk.StringVar(value="")
        self.session_date_filter = tk.StringVar(value="Todas")
        self._partial_message_active = False
        self.partial_message_start_index: str | None = None
        self.partial_message_body_index: str | None = None
        self.partial_message_role: str | None = None
        self.partial_message_created_at: str | None = None
        self.partial_message_content: str = ""
        self.cancel_event = threading.Event()
        self.status_text = tk.StringVar(value="Listo")
        self.tabular_intent_resolver = TabularIntentResolver()

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
        search_entry = ttk.Entry(sidebar, textvariable=self.session_search_query)
        search_entry.pack(fill=tk.X, pady=(8, 6))
        search_entry.bind("<Return>", self._on_search_enter)

        self.date_filter_combobox = ttk.Combobox(
            sidebar,
            textvariable=self.session_date_filter,
            values=["Todas", "Hoy", "Esta semana", "Este mes"],
            state="readonly",
        )
        self.date_filter_combobox.pack(fill=tk.X, pady=(0, 6))
        self.date_filter_combobox.bind("<<ComboboxSelected>>", self._on_filter_changed)

        search_actions = ttk.Frame(sidebar)
        search_actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(search_actions, text="Buscar", command=self._apply_session_filters).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        ttk.Button(search_actions, text="Limpiar", command=self._clear_session_filters).pack(side=tk.LEFT, expand=True, fill=tk.X)

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

        self._save_current_session_if_needed()
        session = self.session_repository.get_session(self.current_session_id) or session

        normalized_format = self._prompt_export_format()
        if not normalized_format:
            return

        format_map = {
            "txt": (".txt", "Texto", self.conversation_exporter.export_txt),
            "md": (".md", "Markdown", self.conversation_exporter.export_markdown),
            "json": (".json", "JSON", self.conversation_exporter.export_json),
        }

        if normalized_format not in format_map:
            messagebox.showerror("Exportar", "Formato no válido. Usa: txt, md o json.", parent=self.root)
            return

        extension, filetype_label, export_fn = format_map[normalized_format]
        suggested_name = self.conversation_exporter.build_safe_filename(session.get("title", "Sesion"), normalized_format)

        output_path = filedialog.asksaveasfilename(
            title="Exportar conversación",
            defaultextension=extension,
            initialfile=suggested_name,
            filetypes=[(filetype_label, f"*{extension}")],
            parent=self.root,
        )
        if not output_path:
            return

        self.logger.info(
            "Exportación iniciada: sesión=%s formato=%s destino=%s",
            self.current_session_id,
            normalized_format,
            output_path,
        )

        try:
            export_fn(session, output_path)
            self.logger.info(
                "Exportación completada: sesión=%s formato=%s destino=%s",
                self.current_session_id,
                normalized_format,
                output_path,
            )
            messagebox.showinfo("Exportar", "Conversación exportada correctamente.", parent=self.root)
        except Exception:
            self.logger.exception(
                "Error exportando sesión=%s formato=%s destino=%s",
                self.current_session_id,
                normalized_format,
                output_path,
            )
            messagebox.showerror("Exportar", "No se pudo exportar la conversación.", parent=self.root)

    def _prompt_export_format(self) -> str | None:
        choices = {
            "TXT (.txt)": "txt",
            "Markdown (.md)": "md",
            "JSON (.json)": "json",
        }

        dialog = tk.Toplevel(self.root)
        dialog.title("Exportar conversación")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Formato:").grid(row=0, column=0, sticky="w")

        selected_label = tk.StringVar(value="TXT (.txt)")
        format_selector = ttk.Combobox(
            frame,
            textvariable=selected_label,
            values=list(choices.keys()),
            state="readonly",
            width=20,
        )
        format_selector.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        format_selector.current(0)

        result: dict[str, str | None] = {"format": None}

        def on_export() -> None:
            label = selected_label.get().strip()
            result["format"] = choices.get(label)
            dialog.destroy()

        def on_cancel() -> None:
            result["format"] = None
            dialog.destroy()

        ttk.Button(frame, text="Exportar", command=on_export).grid(row=2, column=0, sticky="e", padx=(0, 6))
        ttk.Button(frame, text="Cancelar", command=on_cancel).grid(row=2, column=1, sticky="w")

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        format_selector.focus_set()

        self.root.wait_window(dialog)
        return result["format"]

    def _open_settings_window(self) -> None:
        SettingsDialog(self.root, self._on_settings_saved)

    def _on_settings_saved(self, payload: dict[str, object]) -> None:
        model = normalize_model(str(payload.get("default_model", "")))
        self.model_selector.configure(values=self.app_context.settings.AVAILABLE_MODELS)
        self.model_selector.set(model)
        self.chat_manager.update_runtime_settings(
            system_prompt=str(payload.get("system_prompt", self.app_context.settings.SYSTEM_PROMPT)),
            max_context_messages=int(payload.get("max_context_messages", self.app_context.settings.MAX_CONTEXT_MESSAGES)),
            streaming_enabled=bool(payload.get("streaming_enabled", self.chat_manager.streaming_enabled)),
            api_key=self.app_context.settings.resolve_api_key(),
        )
        self.logger.info("Cambios de configuración aplicados en sesión actual.")

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

        attachments_row = ttk.Frame(bottom)
        attachments_row.grid(row=0, column=0, sticky="ew", pady=(0, 6), padx=(0, 8))
        attachments_row.columnconfigure(1, weight=1)
        ttk.Button(attachments_row, text="Adjuntar", command=self._on_attach_files).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.attachments_label = ttk.Label(attachments_row, text="Adjuntos pendientes: (ninguno)")
        self.attachments_label.grid(row=0, column=1, sticky="w")

        self.input_text = tk.Text(bottom, height=4, wrap=tk.WORD)
        self.input_text.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.input_text.bind("<Control-Return>", self._on_ctrl_enter)

        self.send_button = ttk.Button(bottom, text="Enviar", command=self._on_send)
        self.send_button.grid(row=1, column=1, sticky="ns")
        self.cancel_button = ttk.Button(bottom, text="Cancelar", command=self._on_cancel_generation, state=tk.DISABLED)
        self.cancel_button.grid(row=1, column=2, sticky="ns")
        self.status_label = ttk.Label(bottom, textvariable=self.status_text)
        self.status_label.grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _set_status(self, status: str) -> None:
        self.status_text.set(status)
        self.logger.info("Estado de generación: %s", status)

    def is_document_reference(self, user_text: str) -> bool:
        normalized = (user_text or "").lower()
        return any(term in normalized for term in self.DOCUMENT_REFERENCE_TERMS)

    def _load_initial_sessions(self) -> None:
        self.json_migrator.migrate()
        sessions = self.session_repository.list_sessions()
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
        session = self.session_repository.create_session(model=selected_model)
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
        self.session_repository.rename_session(self.current_session_id, new_title)
        updated = self.session_repository.get_session(self.current_session_id)
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

        self.session_repository.delete_session(session_id)
        self.sessions_by_id.pop(session_id, None)
        if session_id in self.session_order:
            self.session_order.remove(session_id)
        self.current_session_id = None
        self.pending_attachments = []
        self._refresh_attachments_ui()
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
        previous = self.current_session_id
        mapped_filter = {
            "Todas": "all",
            "Hoy": "today",
            "Esta semana": "week",
            "Este mes": "month",
        }
        filter_key = mapped_filter.get(self.session_date_filter.get(), "all")
        query = self.session_search_query.get().strip()
        results = self.session_repository.search_sessions(query=query, date_filter=filter_key)
        self.session_list_items = results

        self.session_listbox.delete(0, tk.END)
        for item in results:
            session_id = item["id"]
            if session_id not in self.sessions_by_id:
                maybe_session = self.session_repository.get_session(session_id)
                if maybe_session:
                    self.sessions_by_id[session_id] = maybe_session
            title = item.get("title", "Nueva sesión")
            updated_label = self._format_sidebar_datetime(item.get("updated_at"))
            message_count = int(item.get("message_count", 0))
            suffix = "mensaje" if message_count == 1 else "mensajes"
            display = f"{title} | {updated_label} | {message_count} {suffix}"
            self.session_listbox.insert(tk.END, display)

        if previous:
            for index, item in enumerate(self.session_list_items):
                if item.get("id") == previous:
                    self.session_listbox.selection_set(index)
                    self.session_listbox.activate(index)
                    break

    def _format_sidebar_datetime(self, value: str | None) -> str:
        if not value:
            return "-"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value

    def _on_search_enter(self, event: tk.Event) -> str:
        self._apply_session_filters()
        return "break"

    def _on_filter_changed(self, event: tk.Event) -> None:
        self._apply_session_filters()

    def _apply_session_filters(self) -> None:
        self._refresh_session_listbox()

    def _clear_session_filters(self) -> None:
        self.session_search_query.set("")
        self.session_date_filter.set("Todas")
        self._refresh_session_listbox()

    def _select_session(self, session_id: str) -> None:
        loaded_session = self.session_repository.get_session(session_id) or self.sessions_by_id.get(session_id)
        if not loaded_session:
            return
        self.sessions_by_id[session_id] = loaded_session
        self.current_session_id = session_id

        self.session_listbox.selection_clear(0, tk.END)
        for index, item in enumerate(self.session_list_items):
            if item.get("id") == session_id:
                self.session_listbox.selection_set(index)
                self.session_listbox.activate(index)
                break

        session_model = normalize_model(loaded_session.get("model"))
        loaded_session["model"] = session_model
        self.model_selector.set(session_model)

        self.chat_manager.conversation_manager.load_messages(loaded_session.get("messages", []))
        self.pending_attachments = []
        self._refresh_attachments_ui()
        self._clear_conversation_view()
        for msg in loaded_session.get("messages", []):
            self.append_message(msg.get("role", "system"), msg.get("content", ""), msg.get("created_at"), msg.get("attachments", []))
        self.logger.info("Sesión seleccionada: %s", session_id)


    def _refresh_attachments_ui(self) -> None:
        if not self.pending_attachments:
            self.attachments_label.configure(text="Adjuntos pendientes: (ninguno)")
            return
        names = [att.get("original_name", "archivo") for att in self.pending_attachments]
        self.attachments_label.configure(text=f"Adjuntos pendientes ({len(names)}): " + ", ".join(names[:3]) + ("..." if len(names) > 3 else ""))

    def _on_attach_files(self) -> None:
        if not self.current_session_id:
            return
        paths = filedialog.askopenfilenames(
            title="Adjuntar documentos",
            filetypes=[("Documentos soportados", "*.txt *.csv *.pdf *.doc *.docx *.xls *.xlsx")],
            parent=self.root,
        )
        if not paths:
            return

        for path in paths:
            try:
                self.attachment_manager.add_attachment(self.current_session_id, path)
            except Exception as exc:
                self.logger.exception("Error adjuntando archivo: %s", path)
                messagebox.showerror("Adjuntos", f"No se pudo adjuntar {path}: {exc}", parent=self.root)

        self.pending_attachments = self.attachment_manager.list_pending_attachments(self.current_session_id)
        self._refresh_attachments_ui()

    def _on_session_select(self, event: tk.Event) -> None:
        if not self.session_listbox.curselection():
            return
        index = self.session_listbox.curselection()[0]
        if index >= len(self.session_list_items):
            return
        session_id = self.session_list_items[index]["id"]
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
        self.session_repository.save_session(session)

    def _on_ctrl_enter(self, event: tk.Event) -> str:
        self._on_send()
        return "break"

    def _on_send(self) -> None:
        user_message = self.input_text.get("1.0", tk.END).strip()
        if not self.current_session_id:
            return
        pending_attachments = list(self.pending_attachments)
        if not user_message and not pending_attachments:
            return
        if not user_message and pending_attachments:
            user_message = f"Archivo adjunto: {pending_attachments[0].get('original_name', 'archivo')}"
            self.logger.info("Envío con solo adjunto: session_id=%s", self.current_session_id)

        user_saved = self._store_message("user", user_message)
        if not user_saved:
            return
        attachment_ids = [att.get("id") for att in pending_attachments if att.get("id")]
        if attachment_ids:
            self.attachment_manager.attach_pending_files_to_message(self.current_session_id, user_saved["id"], attachment_ids)
            user_saved["attachments"] = pending_attachments

        self.append_message("user", user_message, user_saved.get("created_at"), user_saved.get("attachments", []))
        self.pending_attachments = []
        self.logger.info("Limpieza de adjuntos pendientes: session_id=%s", self.current_session_id)
        self._refresh_attachments_ui()
        self.input_text.delete("1.0", tk.END)
        self.send_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.cancel_event.clear()
        self.append_partial_message("assistant", "")
        self._set_status("Preparando adjuntos...")

        model = normalize_model(self.model_selector.get())
        self.model_selector.set(model)
        self.sessions_by_id[self.current_session_id]["model"] = model
        used_attachments = [att for att in pending_attachments if (att.get("extracted_text") or att.get("extracted_path"))]
        use_recent = False
        if not used_attachments and self.is_document_reference(user_message):
            use_recent = True
            self._set_status("Analizando documento...")
            used_attachments = self.attachment_manager.list_recent_message_attachments(
                self.current_session_id,
                limit=int(settings.RECENT_ATTACHMENT_CONTEXT_LIMIT),
            )
            self.logger.info(
                "Uso de adjuntos recientes: session_id=%s detectado_ref=%s total=%s",
                self.current_session_id,
                True,
                len(used_attachments),
            )
        else:
            self.logger.info(
                "Uso de adjuntos pendientes: session_id=%s total=%s",
                self.current_session_id,
                len(used_attachments),
            )
        resolver_result = self.tabular_intent_resolver.resolve(user_message)
        self.logger.info("TabularIntentResolver: mensaje=%s resultado=%s pending=%s contexto=%s", user_message, resolver_result.get("status"), self.tabular_intent_resolver.pending_clarification, self.tabular_intent_resolver.active_table_context)
        resolved_intent = resolver_result.get("intent") if resolver_result.get("status") == "ready" else None
        tabular_risk = self._has_tabular_risk(user_message) and self._has_recent_tabular_attachment(used_attachments)
        if resolver_result.get("status") == "needs_clarification":
            clarification_message = str(resolver_result.get("message", "¿Puedes aclararlo un poco más?"))
            self.update_partial_message(clarification_message)
            self._on_worker_success(clarification_message)
            return
        local_spreadsheet_context = self._build_local_spreadsheet_context(user_message, used_attachments, resolved_intent)
        if tabular_risk and resolver_result.get("status") == "not_tabular":
            self.logger.warning("Bloqueo anti-alucinación: riesgo_tabular=true intent_detectado=false mensaje=%s", user_message)
            clarification = "¿Quieres contar entregas, sumar kilos o sumar importe?"
            self.update_partial_message(clarification)
            self._on_worker_success(clarification)
            return
        if resolved_intent and resolved_intent.get("type") == "table_analysis":
            document_context = local_spreadsheet_context
            self.logger.info("Consulta tabular detectada: se omite contexto textual de adjuntos y se usa solo cálculo local. intent=%s", resolved_intent)
        else:
            document_context = build_document_context(used_attachments)
            if local_spreadsheet_context:
                document_context = f"{document_context}\n\n{local_spreadsheet_context}" if document_context else local_spreadsheet_context
        context_chars = len(document_context)
        self.logger.info(
            "Contexto documental preparado para envío actual: session_id=%s adjuntos=%s chars=%s truncado=%s",
            self.current_session_id,
            len(used_attachments),
            context_chars,
            "sí" if "[Contenido truncado por límite de seguridad]" in document_context else "no",
        )
        if used_attachments:
            names = [att.get("original_name", "archivo") for att in used_attachments]
            label = f"Usando {len(used_attachments)} documento adjunto: {names[0]}" if len(used_attachments) == 1 else f"Usando {len(used_attachments)} documentos adjuntos: {', '.join(names[:3])}"
            self.append_system_message(label)
            self.logger.info(
                "Adjuntos enviados a OpenAI: session_id=%s origen=%s archivos=%s chars=%s",
                self.current_session_id,
                "recientes" if use_recent else "pendientes",
                names,
                context_chars,
            )
        self._set_status("Consultando OpenAI...")
        worker = threading.Thread(target=self._assistant_response_worker, args=(user_message, model, document_context), daemon=True)
        worker.start()

    def _build_local_spreadsheet_context(self, user_message: str, attachments: list[dict], resolved_intent: dict | None) -> str:
        intent = resolved_intent
        if not intent:
            return ""
        if intent.get("type") == "table_clarification_prompt":
            return str(intent.get("message", ""))

        table_attachments = [
            a for a in attachments if a.get("extension", "").lower() in {".xlsx", ".xls", ".csv"}
        ]
        if not table_attachments:
            return ""

        latest = sorted(table_attachments, key=lambda a: a.get("created_at", ""), reverse=True)[0]
        stored_path = latest.get("stored_path")
        if not stored_path:
            return ""

        try:
            self._set_status("Analizando tabla...")
            debug_info = self.table_loader.debug_table_scan(str(stored_path))
            tables = self.table_loader.load_tables(str(stored_path))
            if not tables:
                return ""

            semantic_schema = self.semantic_inference.infer_schema(tables)
            total_rows = sum(len(t.get("rows", [])) for t in tables)
            sheet_names = [t.get("sheet_name", "") for t in tables]
            self.logger.info("TableLoader resumen: hojas_leidas=%s nombres=%s total_filas_estructuradas=%s", len(tables), sheet_names, total_rows)
            self.logger.info("Table analysis: hojas_detectadas=%s intencion=%s semantic=%s", len(tables), intent, semantic_schema)

            self._set_status("Calculando resultados...")
            result = self.table_analysis_engine.run_analysis(tables, intent, semantic_schema=semantic_schema)
            self.tabular_intent_resolver.clear_pending()
            unique_groups = [r.get("group") for r in result.get("result", []) if r.get("group") not in {None, ""}]
            self.logger.info("Table analysis intent_detectado=%s", intent)
            self.logger.info("Table analysis operacion_ejecutada=%s columnas_usadas=%s top_n_aplicado=%s", result.get("operation"), {"group_by": result.get("group_by"), "value_column": result.get("value_column") or result.get("numerator_column")}, result.get("top_n"))
            self.logger.info("Table analysis resultado_local_bruto=%s", result)
            self.logger.info("Table analysis variedades_encontradas=%s detalle=%s", len(unique_groups), unique_groups)
            if intent.get("operation") == "aggregate_sum" and (str(result.get("group_by", "")).lower().startswith("variedad") or str(intent.get("group_by_semantic", "")) == "variety") and len(unique_groups) == 1:
                possible_more_blocks = any(int(sheet.get("blocks_detected", 0)) > 1 for sheet in debug_info.get("sheets", [])) or len(debug_info.get("sheets_found", [])) > 1
                if possible_more_blocks:
                    self.logger.warning("Solo se detectó una variedad con múltiples bloques/hojas. log=%s", debug_info.get("log_path", ""))
                    return "No he podido leer correctamente todas las variedades del archivo. ¿Quieres que lo revisemos con otra columna o con otro archivo?"
            self.logger.info("Table analysis: operacion_ejecutada=%s", intent.get("operation"))
            self.tabular_intent_resolver.update_active_context({
                "session_id": self.current_session_id,
                "attachment_id": latest.get("id"),
                "file_name": latest.get("original_name"),
                "available_columns": sorted({c for t in tables for c in t.get("headers", [])}),
                "semantic_columns": semantic_schema.get("best_semantic_columns", {}),
                "last_metric": intent.get("value_semantic") or intent.get("denominator_semantic"),
                "last_value_column": result.get("value_column") or result.get("denominator_column"),
                "last_group_by": result.get("group_by"),
                "last_operation": result.get("operation") or intent.get("operation"),
            })
            self._set_status("Generando respuesta...")
            lines = [
                "Resultado tabular calculado localmente (determinista):",
                str(result),
                "Estos resultados han sido calculados localmente por Python sobre el Excel completo. Úsalos literalmente. No recalcules, no inventes valores y no digas que no puedes leer el archivo. Estos resultados han sido calculados localmente. No añadas socios, variedades ni valores que no aparezcan en el resultado.",
            ]
            return "\n".join(lines)
        except ValueError as exc:
            self.logger.warning("Error de columnas en análisis tabular: %s", exc)
            return "No pude completar el cálculo con esa tabla. ¿Quieres que lo intentemos con otra dimensión o métrica?"
        except Exception:
            self.logger.exception("Error en motor genérico de análisis tabular")
            return ""


    def _build_semantic_hints(self, intent: dict, semantic_schema: dict) -> str:
        requested = [
            ("group_by_semantic", "agrupación"),
            ("value_semantic", "valor"),
            ("numerator_semantic", "numerador"),
            ("denominator_semantic", "denominador"),
        ]
        for key, label in requested:
            semantic = intent.get(key)
            if not semantic:
                continue
            candidates = []
            for table in semantic_schema.get("tables", []):
                for col, meta in table.get("columns", {}).items():
                    if meta.get("semantic_type") == semantic:
                        candidates.append((col, float(meta.get("confidence", 0.0))))
            candidates.sort(key=lambda x: x[1], reverse=True)
            if not candidates or candidates[0][1] < 0.60 or (len(candidates) > 1 and abs(candidates[0][1]-candidates[1][1]) < 0.05):
                top = ", ".join([f"{c[0]} ({c[1]:.2f})" for c in candidates[:3]]) or "sin candidatos"
                self.logger.warning("Baja confianza semántica semantic=%s candidates=%s", semantic, candidates[:3])
                readable = ", ".join([c[0] for c in candidates[:3]]) or "sin opciones claras"
                return f"No tengo claro qué columna usar para {label}. Veo estas opciones: {readable}. ¿Cuál quieres usar?"
        return ""

    def _normalize_for_match(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _has_tabular_risk(self, user_message: str) -> bool:
        normalized = self._normalize_for_match(user_message)
        return any(term in normalized for term in self.TABULAR_RISK_TERMS)

    def _has_recent_tabular_attachment(self, attachments: list[dict]) -> bool:
        return any(a.get("extension", "").lower() in {".xlsx", ".xls", ".csv"} for a in attachments)

    def _assistant_response_worker(self, user_message: str, model: str, document_context: str) -> None:
        try:
            def on_delta(delta: str) -> None:
                self.root.after(0, lambda d=delta: self.update_partial_message(d))

            if self.chat_manager.streaming_enabled:
                self.root.after(0, lambda: self._set_status("Generando respuesta..."))
                response = self.chat_manager.send_message_streaming(
                    user_text=user_message,
                    model=model,
                    on_delta=on_delta,
                    should_cancel=self.cancel_event.is_set,
                    document_context=document_context,
                )
            else:
                response = self.chat_manager.send_message(user_text=user_message, model=model, document_context=document_context)
                self.root.after(0, lambda r=response: self.update_partial_message(r))
            self.root.after(0, lambda: self._on_worker_success(response))
        except Exception:
            self.logger.exception("Error en worker de asistencia")
            self.root.after(0, self._on_worker_error)

    def _on_worker_success(self, response: str) -> None:
        is_cancelled = self.cancel_event.is_set()
        if is_cancelled:
            self.cancel_partial_message()
        else:
            self.finish_partial_message()

        if response:
            self._store_message("assistant", response)
        self.send_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.cancel_event.clear()
        self._set_status("Listo")

    def _on_worker_error(self) -> None:
        error_msg = "No se pudo obtener respuesta de OpenAI. Revisa la configuración, el modelo o la conexión."
        self.cancel_partial_message()
        self.append_system_message(error_msg)
        self.send_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.cancel_event.clear()
        self._set_status("Error")

    def _on_cancel_generation(self) -> None:
        self.logger.info("Cancelación solicitada por el usuario.")
        self._set_status("Cancelando...")
        self.cancel_event.set()
        self.cancel_button.configure(state=tk.DISABLED)

    def _store_message(self, role: str, content: str) -> dict | None:
        if not self.current_session_id or not content.strip():
            return None
        session = self.sessions_by_id[self.current_session_id]
        msg = {"role": role, "content": content, "created_at": datetime.now(timezone.utc).isoformat()}
        saved = self.session_repository.add_message(self.current_session_id, role, content, msg["created_at"])
        if not saved:
            return None
        if session.get("title") == "Nueva sesión" and role == "user":
            session["title"] = content[:40]
            self.session_repository.rename_session(self.current_session_id, session["title"])
        refreshed = self.session_repository.get_session(self.current_session_id)
        if refreshed:
            self.sessions_by_id[self.current_session_id] = refreshed
        self._refresh_session_listbox()
        return saved

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

    def append_message(self, role: str, content: str, created_at: str | None = None, attachments: list[dict] | None = None) -> None:
        role_key = role if role in self.ROLE_DISPLAY else "system"
        label = self.ROLE_DISPLAY.get(role_key, "Sistema")
        tag = f"header_{role_key}"
        timestamp = self._format_timestamp(created_at)
        cleaned_content = self._clean_markdown_basic(content)

        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.insert(tk.END, f"[{timestamp}] {label}\n", tag)
        if cleaned_content.strip():
            self.conversation_text.insert(tk.END, f"{cleaned_content}\n", "body")
        for attachment in attachments or []:
            self.conversation_text.insert(tk.END, f"📎 {attachment.get('original_name', 'archivo')}\n", "body")
        self.conversation_text.insert(tk.END, "\n", "body")
        self.conversation_text.see(tk.END)
        self.conversation_text.configure(state=tk.DISABLED)

    def append_system_message(self, content: str) -> None:
        self.append_message("system", content)

    def append_user_message(self, content: str) -> None:
        self.append_message("user", content)

    def append_assistant_message(self, content: str) -> None:
        self.append_message("assistant", content)

    def append_partial_message(self, role: str, partial_content: str) -> None:
        if not self._partial_message_active:
            role_key = role if role in self.ROLE_DISPLAY else "system"
            label = self.ROLE_DISPLAY.get(role_key, "Sistema")
            tag = f"header_{role_key}"
            self.partial_message_role = role_key
            self.partial_message_created_at = datetime.now(timezone.utc).isoformat()
            self.partial_message_content = ""
            timestamp = self._format_timestamp(self.partial_message_created_at)
            self.conversation_text.configure(state=tk.NORMAL)
            self.partial_message_start_index = self.conversation_text.index("end-1c")
            if self.partial_message_start_index != "1.0":
                self.conversation_text.insert(tk.END, "\n")
                self.partial_message_start_index = self.conversation_text.index("end-1c")
            self.conversation_text.insert(tk.END, f"[{timestamp}] {label}\n", tag)
            self.partial_message_body_index = self.conversation_text.index(tk.END)
            self._partial_message_active = True
            self.conversation_text.see(tk.END)
            self.conversation_text.configure(state=tk.DISABLED)
        if partial_content:
            self.update_partial_message(partial_content)

    def update_partial_message(self, delta: str) -> None:
        if self.partial_message_start_index is None:
            self.append_partial_message("assistant", "")
        if not self._partial_message_active or not delta:
            return
        cleaned_delta = self._clean_markdown_basic(delta)
        self.partial_message_content += delta
        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.insert(tk.END, cleaned_delta, "body")
        self.conversation_text.see(tk.END)
        self.conversation_text.configure(state=tk.DISABLED)

    def finish_partial_message(self) -> None:
        if self._partial_message_active:
            self.conversation_text.configure(state=tk.NORMAL)
            self.conversation_text.insert(tk.END, "\n\n", "body")
            self.conversation_text.configure(state=tk.DISABLED)
        self._partial_message_active = False
        self.partial_message_start_index = None
        self.partial_message_body_index = None
        self.partial_message_role = None
        self.partial_message_created_at = None
        self.partial_message_content = ""

    def cancel_partial_message(self) -> None:
        if not self._partial_message_active:
            return
        if self.partial_message_content.strip():
            cancel_notice = "\n\n[Generación cancelada]"
            self.partial_message_content += cancel_notice
            self.conversation_text.configure(state=tk.NORMAL)
            self.conversation_text.insert(tk.END, cancel_notice, "body")
            self.conversation_text.insert(tk.END, "\n\n", "body")
            self.conversation_text.configure(state=tk.DISABLED)
        else:
            self.conversation_text.configure(state=tk.NORMAL)
            if self.partial_message_start_index is not None:
                self.conversation_text.delete(self.partial_message_start_index, tk.END)
            self.conversation_text.configure(state=tk.DISABLED)
        self._partial_message_active = False
        self.partial_message_start_index = None
        self.partial_message_body_index = None
        self.partial_message_role = None
        self.partial_message_created_at = None
        self.partial_message_content = ""
