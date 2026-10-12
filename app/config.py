"""Only non-sensitive defaults live in source; actual secrets are environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_SIZE = 20 * 1024 * 1024
NODE_IDS = ('node_a', 'node_b')
NODE_URLS = {
    'node_a': os.getenv('NODE_A_URL', 'https://localhost:8001'),
    'node_b': os.getenv('NODE_B_URL', 'https://localhost:8002'),
}
NODE_SECRETS = {
    'node_a': os.getenv('NODE_A_SECRET') or os.getenv('STORAGE_SERVICE_SECRET'),
    'node_b': os.getenv('NODE_B_SECRET') or os.getenv('STORAGE_SERVICE_SECRET'),
}
CA_BUNDLE = os.getenv('SECURESHARE_CA_BUNDLE')
VERIFY_TLS = str(ROOT / CA_BUNDLE) if CA_BUNDLE and not Path(CA_BUNDLE).is_absolute() else (CA_BUNDLE or True)
ALLOWED_SUFFIXES = {'.pdf', '.txt', '.csv', '.docx', '.xlsx', '.pptx'}
