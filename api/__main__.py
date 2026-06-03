"""Punt d'entrada del backend: `uv run python -m api`.

Arrenca uvicorn al port 8000. El frontend SvelteKit (Vite, port 5173) fa
proxy de /api cap aquí en desenvolupament.
"""
from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("api.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
