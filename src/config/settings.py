from dotenv import load_dotenv

import os

load_dotenv()

APP_NAME = "PROM-9™ Desktop"
APP_VERSION = "0.1.0"
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_ATTACHMENT_MB = 20
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
