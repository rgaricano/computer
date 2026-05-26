<script lang="ts">
    import { onMount } from "svelte";
    import { getWelcome } from "$lib/apis/state";
    import { t } from "$lib/i18n";

    let appVersion = $state("");

    onMount(() => {
        getWelcome()
            .then((d) => {
                appVersion = d.version || "";
            })
            .catch(() => {});
    });
</script>

<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">
    {$t("about.title")}
</h2>

<div>
    <div class="flex items-baseline gap-2">
        <span class="text-xs font-semibold text-gray-900 dark:text-white"
            >cptr</span
        >
        {#if appVersion}
            <span class="text-[11px] text-gray-400 dark:text-gray-600 font-mono"
                >v{appVersion}</span
            >
        {/if}
    </div>
    <p class="text-[13px] text-gray-500 mt-0.5 mb-4">{$t("app.tagline")}</p>

    <h3 class="text-xs text-gray-400 dark:text-gray-600 mb-1">
        {$t("about.license")}
    </h3>
    <p
        class="text-[11px] text-gray-500 leading-relaxed font-mono whitespace-pre-line"
    >
        <a
            href="https://github.com/open-webui/computer/blob/main/LICENSE"
            target="_blank"
            rel="noopener noreferrer"
            class="underline hover:text-gray-700 dark:hover:text-gray-300"
            >Open Use License</a
        >

        <br />
        Copyright © 2026 Open WebUI Inc. All rights reserved.
    </p>
</div>

<p class="text-[11px] text-gray-300 dark:text-gray-700 pt-8">
    {$t("about.createdBy")}
</p>
