<script lang="ts">
    import Icon from "./Icon.svelte";
    import Modal from "./Modal.svelte";
    import Users from "./Admin/Users.svelte";
    import Connections from "./Admin/Connections.svelte";
    import AdminSettings from "./Admin/Settings.svelte";
    import { t } from '$lib/i18n';

    interface Props {
        onclose: () => void;
    }

    let { onclose }: Props = $props();

    let activeTab = $state<"users" | "connections" | "settings">("users");
</script>

<Modal
    {onclose}
    class="w-full max-w-3xl mx-4 md:mx-0 flex flex-col md:flex-row max-h-[85vh] md:h-[560px]"
>
    <nav
        class="shrink-0 border-b md:border-b-0 md:border-r border-gray-200 dark:border-white/6 md:w-[180px]"
    >
        <div class="flex md:flex-col p-1 gap-px">
            <button
                class="flex items-center gap-1.5 h-7 px-2 md:w-full shrink-0 rounded-lg text-xs text-gray-400 dark:text-gray-600 hover:text-gray-700 dark:hover:text-gray-300 transition-colors duration-75 md:mb-1"
                onclick={onclose}
            >
                <Icon name="chevron-left" size={12} />
                <span>{$t('settings.back')}</span>
            </button>
            {#each [{ id: "users", label: $t('admin.users'), icon: "user" }, { id: "connections", label: $t('admin.connections'), icon: "plug" }, { id: "settings", label: $t('admin.settings'), icon: "settings" }] as tab}
                <button
                    class="flex items-center gap-1.5 h-7 px-2 md:w-full shrink-0 rounded-lg text-xs text-left transition-colors duration-75
						{activeTab === tab.id
                        ? 'font-medium text-gray-900 dark:text-white bg-gray-100 dark:bg-white/6'
                        : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
                    onclick={() => (activeTab = tab.id as typeof activeTab)}
                >
                    <Icon name={tab.icon} size={14} />
                    {tab.label}
                </button>
            {/each}
        </div>
    </nav>

    <div class="flex-1 overflow-y-auto min-h-0 p-4 md:px-5">
        {#if activeTab === "users"}
            <Users />
        {:else if activeTab === "connections"}
            <Connections />
        {:else if activeTab === "settings"}
            <AdminSettings />
        {/if}
    </div>
</Modal>
