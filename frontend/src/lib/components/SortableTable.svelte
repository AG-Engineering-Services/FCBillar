<script lang="ts">
	// Taula reutilitzable amb ordenació per columna.
	// columns: { key, label, numeric?, muted?, link?(row)=>string|null, fmt?(val,row)=>string }
	// rows: array d'objectes.
	export let columns: any[] = [];
	export let rows: any[] = [];
	export let initialSortKey: string | null = null;
	export let initialSortDir: 'asc' | 'desc' = 'asc';
	export let emptyText = 'Sense dades';

	let sortKey: string | null = initialSortKey;
	let sortDir: 'asc' | 'desc' = initialSortDir;

	function toggleSort(col: any) {
		if (col.sortable === false) return;
		if (sortKey === col.key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = col.key;
			// Per a columnes numèriques comença en descendent (sol ser el més útil).
			sortDir = col.numeric ? 'desc' : 'asc';
		}
	}

	function rawVal(col: any, row: any): any {
		return col && col.value ? col.value(row) : row[col.key];
	}

	$: sortCol = columns.find((c) => c.key === sortKey);

	function cmp(a: any, b: any): number {
		const va = sortCol ? rawVal(sortCol, a) : a[sortKey as string];
		const vb = sortCol ? rawVal(sortCol, b) : b[sortKey as string];
		const an = va === null || va === undefined || va === '';
		const bn = vb === null || vb === undefined || vb === '';
		if (an && bn) return 0;
		if (an) return 1; // nuls sempre al final
		if (bn) return -1;
		let r: number;
		if (typeof va === 'number' && typeof vb === 'number') r = va - vb;
		else r = String(va).localeCompare(String(vb), 'ca', { numeric: true });
		return sortDir === 'asc' ? r : -r;
	}

	$: sorted = sortKey ? [...rows].sort(cmp) : rows;

	function cellText(col: any, row: any): string {
		const v = col.value ? col.value(row) : row[col.key];
		if (col.fmt) return col.fmt(v, row);
		return v === null || v === undefined ? '' : String(v);
	}
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead class="bg-slate-50 text-slate-500 text-left">
			<tr>
				{#each columns as col}
					<th
						class="px-3 py-2 font-medium select-none {col.sortable === false
							? ''
							: 'cursor-pointer hover:text-slate-800'} {col.numeric ? 'text-right' : ''}"
						on:click={() => toggleSort(col)}
					>
						<span class="inline-flex items-center gap-1 {col.numeric ? 'flex-row-reverse' : ''}">
							{col.label}
							{#if sortKey === col.key}
								<span class="text-slate-400 text-xs">{sortDir === 'asc' ? '▲' : '▼'}</span>
							{/if}
						</span>
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#if sorted.length === 0}
				<tr>
					<td colspan={columns.length} class="px-3 py-6 text-center text-slate-400">{emptyText}</td>
				</tr>
			{:else}
				{#each sorted as row}
					<tr class="border-t border-slate-100 hover:bg-slate-50">
						{#each columns as col}
							<td
							class="px-3 py-2 whitespace-nowrap {col.numeric ? 'text-right' : ''} {col.muted
								? 'text-slate-500'
								: ''} {col.cellClass ? col.cellClass(row) : ''}"
						>
								{#if col.badge}
									{@const b = col.badge(row)}
									{#if b}
										<span
											class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium {b.tone ===
											'win'
												? 'bg-emerald-100 text-emerald-700'
												: b.tone === 'lose'
													? 'bg-slate-100 text-slate-500'
													: 'bg-amber-100 text-amber-700'}">{b.label}</span
										>
									{/if}
								{:else if col.link && col.link(row)}
									<a href={col.link(row)} class="hover:underline">{cellText(col, row)}</a>
								{:else}
									{cellText(col, row)}
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			{/if}
		</tbody>
	</table>
</div>
