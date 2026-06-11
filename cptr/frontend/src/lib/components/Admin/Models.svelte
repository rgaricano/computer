<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		getModelConfig,
		updateModelConfig,
		type ModelConfigEntry
	} from '$lib/apis/admin';
	import { t } from '$lib/i18n';
	import Icon from '../Icon.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	type ParamRow = { key: string; value: string };
	type ModelEntry = {
		id: string;
		name: string;
		provider: string;
		is_active: boolean;
		rows: ParamRow[];
		dirty: boolean;
	};

	let loading = $state(true);
	let saving = $state(false);
	let models = $state<ModelEntry[]>([]);
	let selectedId = $state<string | null>(null);

	let globalRows = $state<ParamRow[]>([]);
	let globalDirty = $state(false);
	let globalExpanded = $state(false);

	let hasDirty = $derived(globalDirty || models.some((m) => m.dirty));

	function parseRows(config: ModelConfigEntry | undefined): ParamRow[] {
		const rp = config?.params?.request_params;
		if (!rp || typeof rp !== 'object') return [];
		return Object.entries(rp).map(([key, value]) => ({
			key,
			value: typeof value === 'object' ? JSON.stringify(value) : String(value)
		}));
	}

	function rowsToRequestParams(rows: ParamRow[]): Record<string, unknown> {
		const result: Record<string, unknown> = {};
		for (const { key, value } of rows) {
			if (!key.trim()) continue;
			try {
				result[key.trim()] = JSON.parse(value);
			} catch {
				result[key.trim()] = value;
			}
		}
		return result;
	}

	onMount(async () => {
		try {
			const data = await getModelConfig();
			const config = data.config || {};
			globalRows = parseRows(config['*']);
			globalExpanded = globalRows.length > 0;
			models = data.models.map((m) => {
				const mc = config[m.id];
				return {
					...m,
					is_active: mc?.is_active !== false,
					rows: parseRows(mc),
					dirty: false
				};
			});
		} catch {
			toast.error($t('models.failedToLoad'));
		} finally {
			loading = false;
		}
	});

	async function toggleModel(e: Event, model: ModelEntry) {
		e.stopPropagation();
		const newVal = !model.is_active;
		model.is_active = newVal;
		models = [...models];
		try {
			await updateModelConfig(model.id, { is_active: newVal });
		} catch {
			model.is_active = !newVal;
			models = [...models];
			toast.error($t('models.failedToToggle'));
		}
	}

	async function saveAll() {
		saving = true;
		try {
			const promises: Promise<unknown>[] = [];
			if (globalDirty) {
				const rp = rowsToRequestParams(globalRows);
				promises.push(
					updateModelConfig('*', {
						params: Object.keys(rp).length ? { request_params: rp } : {}
					})
				);
			}
			for (const model of models) {
				if (model.dirty) {
					const rp = rowsToRequestParams(model.rows);
					promises.push(
						updateModelConfig(model.id, {
							params: Object.keys(rp).length ? { request_params: rp } : {}
						})
					);
				}
			}
			await Promise.all(promises);
			globalDirty = false;
			models.forEach((m) => (m.dirty = false));
			toast.success($t('settings.saved'));
		} catch {
			toast.error($t('models.failedToSave'));
		} finally {
			saving = false;
		}
	}
</script>

{#snippet paramRows(rows: ParamRow[], onInput: () => void, onRemove: (i: number) => void, onAdd: () => void)}
	<div class="mb-2">
		<span class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide">request params</span>
		{#each rows as row, i}
			<div class="group/row flex items-center gap-1.5 h-6">
				<input type="text" placeholder="key" bind:value={row.key} oninput={onInput} autocomplete="off" spellcheck="false"
					class="w-24 shrink-0 bg-transparent text-[11px] font-mono text-gray-500 dark:text-gray-500 placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-none" />
				<input type="text" placeholder="value" bind:value={row.value} oninput={onInput} autocomplete="off" spellcheck="false"
					class="flex-1 min-w-0 bg-transparent text-[11px] font-mono text-gray-500 dark:text-gray-500 placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-none" />
				<button type="button" onclick={() => onRemove(i)}
					class="shrink-0 text-gray-300 dark:text-gray-700 opacity-0 group-hover/row:opacity-100 hover:text-gray-500 dark:hover:text-gray-400 transition-colors duration-75" aria-label="Remove">
					<Icon name="xmark" size={8} />
				</button>
			</div>
		{/each}
		<button
			class="flex items-center gap-1 h-6 text-[11px] text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400 transition-colors duration-75"
			onclick={onAdd}
		>
			<Icon name="plus" size={10} />
			<span>Add</span>
		</button>
	</div>
{/snippet}

<div class="flex flex-col h-full">
	{#if loading}
		<div class="flex justify-center py-8"><Spinner size={16} /></div>
	{:else}
		<div class="flex-1 min-h-0 overflow-y-auto">
			<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">{$t('admin.models')}</h2>
			<!-- Global defaults -->
			<button
				class="group flex items-center gap-2 w-full h-7 text-left"
				onclick={() => (globalExpanded = !globalExpanded)}
			>
				<span class="flex-1 text-[13px] text-gray-500 dark:text-gray-400">{$t('models.defaults')}</span>
				{#if globalRows.filter((r) => r.key.trim()).length > 0}
					<span class="text-[10px] text-gray-400 dark:text-gray-600">{globalRows.filter((r) => r.key.trim()).length}</span>
				{/if}
				<Icon name={globalExpanded ? 'chevron-down' : 'chevron-right'} size={10} class="shrink-0 text-gray-300 dark:text-gray-700" />
			</button>

			{#if globalExpanded}
				{@render paramRows(
					globalRows,
					() => (globalDirty = true),
					(i) => { globalRows = globalRows.filter((_, idx) => idx !== i); globalDirty = true; },
					() => { globalRows = [...globalRows, { key: '', value: '' }]; globalDirty = true; }
				)}
			{/if}

			<!-- Per-model list -->
			{#each models as model}
				<button
					class="group flex items-center gap-2 w-full h-7 text-left"
					onclick={() => (selectedId = selectedId === model.id ? null : model.id)}
				>
					<span class="flex-1 text-[13px] truncate {model.is_active ? 'text-gray-700 dark:text-gray-300' : 'text-gray-400 dark:text-gray-600'}">
						{model.name}
					</span>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<span
						class="relative w-6 h-3.5 rounded-full shrink-0 cursor-pointer transition-colors duration-150
							{model.is_active ? 'bg-gray-900 dark:bg-white' : 'bg-gray-200 dark:bg-gray-700'}"
						role="switch" tabindex="-1" aria-checked={model.is_active}
						onclick={(e) => toggleModel(e, model)}
						onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleModel(e, model); } }}
					>
						<span class="absolute top-0.5 w-2.5 h-2.5 rounded-full transition-all duration-150
							{model.is_active ? 'left-3 bg-white dark:bg-gray-900' : 'left-0.5 bg-white dark:bg-gray-500'}"></span>
					</span>
				</button>

				{#if selectedId === model.id}
					{@render paramRows(
						model.rows,
						() => (model.dirty = true),
						(i) => { model.rows = model.rows.filter((_, idx) => idx !== i); model.dirty = true; },
						() => { model.rows = [...model.rows, { key: '', value: '' }]; model.dirty = true; }
					)}
				{/if}
			{/each}

			{#if models.length === 0}
				<p class="text-[13px] text-gray-400 dark:text-gray-600 py-4">{$t('models.noModels')}</p>
			{/if}
		</div>

		<div class="shrink-0 pt-3 flex justify-end">
			<button
				class="text-[13px] text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors duration-100"
				onclick={saveAll}
			>
				{#if saving}{$t('settings.saving')}{:else}{$t('settings.save')}{/if}
			</button>
		</div>
	{/if}
</div>


