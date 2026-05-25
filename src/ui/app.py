import tkinter as tk

from src.config import settings
from src.core.app_context import AppContext
from src.ui.main_window import MainWindow
from src.utils.logger import setup_logging


def run_app() -> None:
    setup_logging()
    app_context = AppContext.create(settings=settings)

    root = tk.Tk()
    MainWindow(root=root, app_context=app_context)
    root.mainloop()
