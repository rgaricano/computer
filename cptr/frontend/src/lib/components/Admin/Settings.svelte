<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount } from 'svelte';
	import { getAdminConfig, updateConfig as apiUpdateConfig } from '$lib/apis/admin';
	import { t } from '$lib/i18n';

	let config = $state<Record<string, any>>({});
	let loading = $state(true);
	let saving = $state(false);

	async function loadConfig() {
		try {
			config = await getAdminConfig();
		} catch { toast.error($t('admin.failedToLoadConfig')); }
		finally { loading = false; }
	}

	async function updateConfig(key: string, value: any) {
		saving = true;
		try {
			await apiUpdateConfig({ [key]: value });
			config[key] = value;
			toast.success($t('settings.saved'));
		} catch { toast.error($t('admin.failedToSave')); }
		finally { saving = false; }
	}

	onMount(loadConfig);
</script>

<div class="flex flex-col min-h-full">
<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">{$t('admin.settings')}</h2>

{#if loading}
	<div class="flex justify-center py-8">
		<div class="w-4 h-4 border-2 border-gray-300 border-t-gray-600 dark:border-gray-700 dark:border-t-gray-400 rounded-full animate-spin"></div>
	</div>
{:else}
	<!-- Auth settings -->
	<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2">{$t('admin.authentication')}</h3>

	<div class="flex items-center justify-between h-8">
		<span class="text-[13px] text-gray-700 dark:text-gray-300">{$t('admin.allowSignUp')}</span>
		<button
			class="relative w-8 h-[18px] rounded-full transition-colors duration-150
				{config['auth.signup_enabled'] ? 'bg-gray-900 dark:bg-white' : 'bg-gray-300 dark:bg-gray-700'}"
			onclick={() => updateConfig('auth.signup_enabled', !config['auth.signup_enabled'])}
			disabled={saving}
		>
			<span
				class="absolute top-[2px] w-[14px] h-[14px] rounded-full transition-all duration-150
					{config['auth.signup_enabled'] ? 'left-[17px] bg-white dark:bg-black' : 'left-[2px] bg-white dark:bg-gray-500'}"
			></span>
		</button>
	</div>
	<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-0.5">
		{config['auth.signup_enabled'] ? $t('admin.signUpEnabled') : $t('admin.signUpDisabled')}
	</p>

	<div class="mt-auto pt-6 flex justify-end">
		<button
			class="text-[13px] text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors duration-100"
			onclick={() => toast.success($t('settings.saved'))}
		>{$t('settings.save')}</button>
	</div>
{/if}
</div>
