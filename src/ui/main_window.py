import logging
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from src.managers.chat_manager import ChatManager
from src.managers.session_storage import SessionStorage


class MainWindow:
    ROLE_DISPLAY = {
        "system": "Sistema",
        "user": "Tú",
        "assistant": "PROM-9",
    }

    def __init__(self, root: tk.Tk, app_context) -> None:
        self.root = root
        self.app_context = app_context
        self.logger = logging.getLogger(__name__)

        self.chat_manager = ChatManager()
        self.session_storage = SessionStorage()

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
        ttk.Button(sidebar, text="Nueva sesión", command=self._new_session).pack(fill=tk.X, pady=(8, 8))

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

        self.conversation_text = tk.Text(conversation_frame, wrap=tk.WORD, state=tk.DISABLED, padx=12, pady=10, spacing1=2, spacing3=8)
        self.conversation_text.grid(row=0, column=0, sticky="nsew")
        self.conversation_text.tag_configure("header_user", foreground="#1d4ed8", font=("Segoe UI", 10, "bold"))
        self.conversation_text.tag_configure("header_assistant", foreground="#047857", font=("Segoe UI", 10, "bold"))
        self.conversation_text.tag_configure("header_system", foreground="#7c3aed", font=("Segoe UI", 10, "bold"))
        self.conversation_text.tag_configure("body", font=("Segoe UI", 10), lmargin1=4, lmargin2=4, spacing3=12)

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

    def _load_initial_sessions(self) -> None:
        sessions = self.session_storage.list_sessions()
        if not sessions:
            self._new_session()
            return

        for session in sessions:
            self._cache_session(session)
        self._refresh_session_listbox()
        self._select_session(self.session_order[0])

    def _new_session(self) -> None:
        self.chat_manager.reset_conversation()
        self._clear_conversation_view()
        session = self.session_storage.create_session(model=self.model_selector.get())
        self.session_storage.save_session(session)
        self._cache_session(session, prepend=True)
        self._refresh_session_listbox()
        self._select_session(session["id"])
        self.append_system_message("Nueva sesión creada.")

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
        self.current_session_id = session_id
        index = self.session_order.index(session_id)
        self.session_listbox.selection_clear(0, tk.END)
        self.session_listbox.selection_set(index)
        self.session_listbox.activate(index)

        session = self.sessions_by_id[session_id]
        if session.get("model"):
            self.model_selector.set(session["model"])

        self.chat_manager.reset_conversation()
        self.chat_manager.conversation_manager.load_messages(session.get("messages", []))

        self._clear_conversation_view()
        for msg in session.get("messages", []):
            self.append_message(msg.get("role", "system"), msg.get("content", ""), msg.get("created_at"))

    def _on_session_select(self, event: tk.Event) -> None:
        if not self.session_listbox.curselection():
            return
        index = self.session_listbox.curselection()[0]
        session_id = self.session_order[index]
        if session_id != self.current_session_id:
            self._select_session(session_id)

    def _on_ctrl_enter(self, event: tk.Event) -> str:
        self._on_send()
        return "break"

    def _on_send(self) -> None:
        user_message = self.input_text.get("1.0", tk.END).strip()
        if not user_message or not self.current_session_id:
            return

        self.logger.info("Mensaje enviado por el usuario.")
        self.append_user_message(user_message)
        self._store_message("user", user_message)
        self.input_text.delete("1.0", tk.END)
        self.send_button.configure(state=tk.DISABLED)

        model = self.model_selector.get()
        self.sessions_by_id[self.current_session_id]["model"] = model
        worker = threading.Thread(
            target=self._assistant_response_worker,
            args=(user_message, model),
            daemon=True,
        )
        worker.start()

    def _assistant_response_worker(self, user_message: str, model: str) -> None:
        try:
            response = self.chat_manager.send_message(user_message, model)
            self.root.after(0, lambda: self._on_worker_success(response))
        except Exception as exc:
            self.logger.exception("Error en worker de asistencia: %s", exc)
            self.root.after(0, self._on_worker_error)

    def _on_worker_success(self, response: str) -> None:
        self.append_assistant_message(response)
        self._store_message("assistant", response)
        self.send_button.configure(state=tk.NORMAL)

    def _on_worker_error(self) -> None:
        error_msg = "No se pudo obtener respuesta de OpenAI. Revisa la configuración, el modelo o la conexión."
        self.append_system_message(error_msg)
        self._store_message("system", error_msg)
        self.send_button.configure(state=tk.NORMAL)

    def _store_message(self, role: str, content: str) -> None:
        if not self.current_session_id:
            return
        session = self.sessions_by_id[self.current_session_id]
        msg = {
            "role": role,
            "content": content,
            "created_at": datetime.now().isoformat(),
        }
        session.setdefault("messages", []).append(msg)

        if role == "user" and session.get("title") == "Nueva sesión" and content.strip():
            session["title"] = content.strip()[:40]
            self._refresh_session_listbox()
            self._select_session(self.current_session_id)

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

    def append_partial_message(self, role: str, content: str) -> None:
        if self.partial_message_start_index is None:
            self.append_message(role, content)
            self.partial_message_start_index = self.conversation_text.index("end-2l")
            return
        self.conversation_text.configure(state=tk.NORMAL)
        self.conversation_text.delete(self.partial_message_start_index, "end-1c")
        self.conversation_text.insert(self.partial_message_start_index, self._clean_markdown_basic(content))
        self.conversation_text.see(tk.END)
        self.conversation_text.configure(state=tk.DISABLED)

    def finish_partial_message(self) -> None:
        self.partial_message_start_index = None

    def append_system_message(self, content: str) -> None:
        self.append_message("system", content)

    def append_user_message(self, content: str) -> None:
        self.append_message("user", content)

    def append_assistant_message(self, content: str) -> None:
        self.append_message("assistant", content)
