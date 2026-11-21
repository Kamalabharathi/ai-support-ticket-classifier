import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    model_provider: str = os.getenv('MODEL_PROVIDER', 'ollama')
    ollama_base_url: str = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    ollama_model: str = os.getenv('OLLAMA_MODEL', 'qwen3:4b')
    database_path: str = os.getenv('DATABASE_PATH', './tickets.db')
    review_threshold: float = float(os.getenv('REVIEW_THRESHOLD', '0.80'))
    cors_origins: tuple[str, ...] = tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000').split(',') if x.strip())

settings = Settings()
