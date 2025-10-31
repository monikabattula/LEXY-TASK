import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file - try multiple locations
backend_dir = Path(__file__).parent.parent.parent  # backend/
root_dir = backend_dir.parent  # project root

# Try loading from backend/.env first, then root/.env
env_paths = [
    backend_dir / ".env",
    root_dir / ".env",
    backend_dir / ".env.local",  # local overrides
]

loaded = False
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        loaded = True
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Loaded .env file from: {env_path}")
        break

if not loaded:
    # If no .env found, try loading from current directory (for backward compatibility)
    load_dotenv(override=False)
    import logging
    logger = logging.getLogger(__name__)
    if os.getenv("GEMINI_API_KEY"):
        logger.info("Loaded environment variables from current directory")
    else:
        logger.warning(
            "No .env file found. Please create one in backend/ or project root with GEMINI_API_KEY"
        )


class Settings:
    app_env: str = os.getenv("APP_ENV", "dev")
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data")).resolve()
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(os.getenv('DATA_DIR', './data')).resolve() / 'app.db'}".replace('\\', '/'),
    )

    # Ensure base directories exist
    uploads_dir: Path = data_dir / "uploads"
    parsed_dir: Path = data_dir / "parsed"
    sessions_dir: Path = data_dir / "sessions"
    outputs_dir: Path = data_dir / "outputs"
    previews_dir: Path = data_dir / "previews"

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")

    def ensure_dirs(self) -> None:
        for p in [
            self.data_dir,
            self.uploads_dir,
            self.parsed_dir,
            self.sessions_dir,
            self.outputs_dir,
            self.previews_dir,
        ]:
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()


