// Client API minimalista: el proxy de Vite reenvia /api → :8000 en dev.
export async function api<T = any>(path: string): Promise<T> {
	const res = await fetch(path);
	if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
	return res.json();
}

export async function apiSend<T = any>(
	path: string,
	method: 'POST' | 'PUT' | 'DELETE',
	body?: unknown
): Promise<T> {
	const res = await fetch(path, {
		method,
		headers: body ? { 'Content-Type': 'application/json' } : undefined,
		body: body ? JSON.stringify(body) : undefined
	});
	if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
	return res.json();
}
