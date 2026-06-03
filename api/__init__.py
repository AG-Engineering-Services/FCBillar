"""Backend HTTP (FastAPI) de FCBillar.

Serveix la mateixa BD SQLite que l'app d'escriptori, reutilitzant la capa
`desktop.models.data_source.DataSource` (que no depèn de Qt). El frontend
SvelteKit consumeix aquests endpoints sota /api.
"""
