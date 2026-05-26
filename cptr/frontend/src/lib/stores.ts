/**
 * Workspace + Tab state management for cptr.
 *
 * State is persisted server-side at /api/state so closing the browser
 * loses nothing. Any device can reconnect and see the same state.
 *
 * Architecture:
 *   Workspace → EditorGroup[] (1 or more groups, each with independent tabs)
 *   Each group has its own tab list and active tab — like VS Code editor groups.
 *   When there are 2+ groups, a split view is rendered.
 */

import { writable, derived, get } from 'svelte/store';
import { getState, saveState } from '$lib/apis/state';
import { listSessions, createSession, deleteSession } from '$lib/apis/terminal';
import { changeLocale, i18next } from '$lib/i18n';

// ── Types ───────────────────────────────────────────────────────

export interface Tab {
	id: string;
	type: 'files' | 'terminal' | 'file' | 'git' | 'chat' | 'preview';
	label: string;
	filePath?: string;
	path?: string;        // generic path (e.g. for chat)
	sessionId?: string;
	port?: number;
	unsaved?: boolean;
	permanent?: boolean;
	badge?: number;
}

export type SplitDirection = 'horizontal' | 'vertical';

export interface EditorGroup {
	id: string;
	tabs: Tab[];
	activeTabId: string;
	tabHistory?: string[]; // MRU stack of tab IDs (most recent last)
}

export interface WorkspaceState {
	id: string;
	name: string;
	path: string;
	groups: EditorGroup[];
	activeGroupId: string;
	splitDirection: SplitDirection;
	splitRatio: number; // 0-1, fraction for the first group
	fileBrowserCwd: string;
	// Legacy fields (kept for migration only)
	tabs?: Tab[];
	activeTabId?: string;
	splitTabId?: string | null;
	tabHistory?: string[];
}

export type Theme = 'dark' | 'light' | 'system';

// ── ID generation ───────────────────────────────────────────────

let _idCounter = Date.now();
function nextId(): string {
	return (++_idCounter).toString(36);
}

// ── Default group for a workspace ───────────────────────────────

function createDefaultGroup(): EditorGroup {
	return {
		id: 'default',
		tabs: [{ id: 'files', type: 'files', label: 'Files', permanent: true }],
		activeTabId: 'files',
	};
}

// ── Stores (initialized empty, hydrated from server) ────────────

export const workspaces = writable<WorkspaceState[]>([]);
export const activeWorkspaceId = writable<string | null>(null);
export const sidebarOpen = writable(typeof window !== 'undefined' ? window.innerWidth >= 768 : false);
export const theme = writable<Theme>('dark');
export const autoApproveTools = writable(false);
export const stateLoaded = writable(false);
export const gitReviewOpen = writable(false);
export const isGitRepo = writable(false);

export const activeWorkspace = derived(
	[workspaces, activeWorkspaceId],
	([$workspaces, $activeId]) => $workspaces.find((w) => w.id === $activeId) ?? null
);

export const activeGroup = derived(activeWorkspace, ($ws) =>
	$ws ? $ws.groups.find((g) => g.id === $ws.activeGroupId) ?? $ws.groups[0] ?? null : null
);

export const activeTab = derived(activeGroup, ($g) =>
	$g ? $g.tabs.find((t) => t.id === $g.activeTabId) ?? null : null
);

export const splitActive = derived(activeWorkspace, ($ws) =>
	($ws?.groups.length ?? 0) > 1
);

// ── Compat aliases for old split-pane API ──────────────────────
// These map to the new groups model so existing imports keep working.

/** @deprecated Use splitActive */
export const splitPaneOpen = splitActive;

/** @deprecated — the "split tab" is now the active tab of the second group */
export const splitTab = derived(activeWorkspace, ($ws) => {
	if (!$ws || $ws.groups.length < 2) return null;
	const secondGroup = $ws.groups.find((g) => g.id !== $ws.activeGroupId) ?? $ws.groups[1];
	return secondGroup?.tabs.find((t) => t.id === secondGroup.activeTabId) ?? null;
});

/** @deprecated Use splitCurrentTab or openInGroup */
export function openTabInSplit(tabId: string, direction?: SplitDirection): void {
	const ws = get(activeWorkspace);
	if (!ws) return;

	// If already split, move tab to the other group
	if (ws.groups.length > 1) {
		const otherGroup = ws.groups.find((g) => g.id !== ws.activeGroupId);
		if (otherGroup) {
			moveTabToGroup(tabId, ws.activeGroupId, otherGroup.id);
			return;
		}
	}

	// Otherwise, create a new group with this tab
	const wsId = get(activeWorkspaceId)!;
	const dir = direction ?? ws.splitDirection ?? 'horizontal';

	// Find the tab in any group
	let sourceTab: Tab | undefined;
	for (const g of ws.groups) {
		sourceTab = g.tabs.find((t) => t.id === tabId);
		if (sourceTab) break;
	}
	if (!sourceTab) return;

	const newTab: Tab = { ...sourceTab, id: nextId(), permanent: false };
	const newGroup: EditorGroup = {
		id: nextId(),
		tabs: [newTab],
		activeTabId: newTab.id,
	};

	workspaces.update((list) =>
		list.map((w) => {
			if (w.id !== wsId) return w;
			return {
				...w,
				groups: [...w.groups, newGroup],
				activeGroupId: newGroup.id,
				splitDirection: dir,
				splitRatio: w.splitRatio ?? 0.5,
			};
		})
	);
}

/** @deprecated Use closeGroup */
export function closeSplitPane(): void {
	const ws = get(activeWorkspace);
	if (!ws || ws.groups.length < 2) return;
	// Close all groups except the first, merging tabs
	const firstGroup = ws.groups[0];
	for (const g of ws.groups.slice(1)) {
		closeGroup(g.id);
	}
}

/** @deprecated No direct equivalent — swap active group focus */
export function swapSplitPanes(): void {
	const ws = get(activeWorkspace);
	if (!ws || ws.groups.length < 2) return;
	const otherGroup = ws.groups.find((g) => g.id !== ws.activeGroupId);
	if (otherGroup) setActiveGroup(otherGroup.id);
}

/** @deprecated Use activeGroup */
export const focusedPane = derived(activeWorkspace, ($ws) =>
	$ws?.activeGroupId === $ws?.groups[0]?.id ? 'main' : 'split'
);

// ── MRU tab history helpers ─────────────────────────────────────

function pushTabHistory(group: EditorGroup, tabId: string): string[] {
	const history = (group.tabHistory ?? []).filter((id) => id !== tabId);
	history.push(tabId);
	if (history.length > 50) history.splice(0, history.length - 50);
	return history;
}

// ── Server-side persistence ─────────────────────────────────────

let _saveTimer: ReturnType<typeof setTimeout> | null = null;

function persistToServer(): void {
	if (_saveTimer) clearTimeout(_saveTimer);
	_saveTimer = setTimeout(() => {
		const state = {
			workspaces: get(workspaces),
			activeWorkspaceId: get(activeWorkspaceId),
			theme: get(theme),
			sidebarOpen: get(sidebarOpen),
			autoApproveTools: get(autoApproveTools),
			locale: i18next.language,
		};
		saveState(state).catch(() => {});
	}, 300);
}

let _subscribed = false;
function subscribeForPersistence() {
	if (_subscribed) return;
	_subscribed = true;
	workspaces.subscribe(() => { if (get(stateLoaded)) persistToServer(); });
	activeWorkspaceId.subscribe(() => { if (get(stateLoaded)) persistToServer(); });
	theme.subscribe(() => { if (get(stateLoaded)) persistToServer(); });
	sidebarOpen.subscribe(() => { if (get(stateLoaded)) persistToServer(); });
	autoApproveTools.subscribe(() => { if (get(stateLoaded)) persistToServer(); });
	i18next.on('languageChanged', () => { if (get(stateLoaded)) persistToServer(); });
}

// ── Migration helper ────────────────────────────────────────────

function migrateWorkspace(ws: any): WorkspaceState {
	// Already migrated to groups model
	if (ws.groups?.length) {
		return {
			...ws,
			splitDirection: ws.splitDirection ?? 'horizontal',
			splitRatio: ws.splitRatio ?? 0.5,
		};
	}

	// Legacy: flat tabs array → single group
	const tabs: Tab[] = ws.tabs ?? [{ id: 'files', type: 'files', label: 'Files', permanent: true }];
	const activeTabId: string = ws.activeTabId ?? 'files';
	const group: EditorGroup = {
		id: 'default',
		tabs,
		activeTabId,
		tabHistory: ws.tabHistory,
	};

	return {
		id: ws.id,
		name: ws.name,
		path: ws.path,
		groups: [group],
		activeGroupId: 'default',
		splitDirection: (ws.splitDirection as SplitDirection) ?? 'horizontal',
		splitRatio: ws.splitRatio ?? 0.5,
		fileBrowserCwd: ws.fileBrowserCwd ?? ws.path,
	};
}

export async function loadStateFromServer(): Promise<void> {
	try {
		const state = await getState();

		if (state.workspaces?.length) {
			const migrated = state.workspaces.map(migrateWorkspace);

			// Validate terminal sessions are still alive
			let aliveSessions: Set<string> = new Set();
			try {
				const sessions = await listSessions();
				aliveSessions = new Set(sessions.map((s) => s.session_id));
			} catch {}

			// Remove dead terminal tabs from all groups
			const cleaned = migrated.map((ws: WorkspaceState) => ({
				...ws,
				groups: ws.groups.map((g) => {
					const filteredTabs = g.tabs.filter((t: Tab) => {
						if (t.type === 'terminal' && t.sessionId && !aliveSessions.has(t.sessionId)) {
							return false;
						}
						return true;
					});
					const activeStillExists = filteredTabs.some((t: Tab) => t.id === g.activeTabId);
					return {
						...g,
						tabs: filteredTabs,
						activeTabId: activeStillExists ? g.activeTabId : (filteredTabs[0]?.id ?? 'files'),
					};
				}).filter((g) => g.tabs.length > 0), // Remove empty groups
			})).map((ws) => ({
				...ws,
				// Ensure at least one group exists
				groups: ws.groups.length > 0 ? ws.groups : [createDefaultGroup()],
				activeGroupId: ws.groups.some((g: EditorGroup) => g.id === ws.activeGroupId) ? ws.activeGroupId : ws.groups[0]?.id ?? 'default',
			}));

			workspaces.set(cleaned);
		}
		if (state.activeWorkspaceId) activeWorkspaceId.set(state.activeWorkspaceId);
		if (state.theme) theme.set(state.theme);
		if (state.sidebarOpen !== undefined) sidebarOpen.set(state.sidebarOpen);
		if (state.autoApproveTools !== undefined) autoApproveTools.set(state.autoApproveTools);
		if (state.locale) changeLocale(state.locale);
	} catch {
		// First run, no state yet
	}

	stateLoaded.set(true);
	subscribeForPersistence();
}

// ── Theme application ───────────────────────────────────────────

function applyTheme(t: Theme) {
	if (typeof window === 'undefined') return;
	let resolved = t;
	if (t === 'system') {
		resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
	}
	document.documentElement.classList.toggle('dark', resolved === 'dark');
	document.documentElement.style.colorScheme = resolved;
	const meta = document.querySelector('meta[name="theme-color"]');
	if (meta) meta.setAttribute('content', resolved === 'dark' ? '#0d0d0d' : '#ffffff');
}

theme.subscribe(applyTheme);

if (typeof window !== 'undefined') {
	window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
		if (get(theme) === 'system') applyTheme('system');
	});
}

// ── Workspace actions ───────────────────────────────────────────

export function addWorkspace(path: string): WorkspaceState {
	const existing = get(workspaces).find((w) => w.path === path);
	if (existing) {
		activeWorkspaceId.set(existing.id);
		return existing;
	}

	const name = path.split('/').filter(Boolean).pop() || path;
	const ws: WorkspaceState = {
		id: nextId(),
		name,
		path,
		groups: [createDefaultGroup()],
		activeGroupId: 'default',
		splitDirection: 'horizontal',
		splitRatio: 0.5,
		fileBrowserCwd: path,
	};
	workspaces.update((list) => [...list, ws]);
	activeWorkspaceId.set(ws.id);
	return ws;
}

export function removeWorkspace(id: string): void {
	workspaces.update((list) => list.filter((w) => w.id !== id));
	const current = get(activeWorkspaceId);
	if (current === id) {
		const remaining = get(workspaces);
		activeWorkspaceId.set(remaining.length > 0 ? remaining[0].id : null);
	}
}

export function reorderWorkspaces(oldIndex: number, newIndex: number): void {
	workspaces.update((list) => {
		const reordered = [...list];
		const [moved] = reordered.splice(oldIndex, 1);
		reordered.splice(newIndex, 0, moved);
		return reordered;
	});
}

export function setActiveWorkspace(id: string): void {
	activeWorkspaceId.set(id);
}

export function updateWorkspace(id: string, partial: Partial<WorkspaceState>): void {
	workspaces.update((list) =>
		list.map((w) => (w.id === id ? { ...w, ...partial } : w))
	);
}

// ── Internal: update a group's tabs ─────────────────────────────

function updateGroupTabs(
	groupId: string | undefined,
	fn: (tabs: Tab[], group: EditorGroup) => { tabs: Tab[]; activeTabId?: string; tabHistory?: string[] }
): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;

	workspaces.update((list) =>
		list.map((ws) => {
			if (ws.id !== wsId) return ws;
			const gid = groupId ?? ws.activeGroupId;
			return {
				...ws,
				groups: ws.groups.map((g) => {
					if (g.id !== gid) return g;
					const result = fn(g.tabs, g);
					const newActiveId = result.activeTabId ?? g.activeTabId;
					const tabHistory = result.tabHistory
						?? (newActiveId !== g.activeTabId
							? pushTabHistory(g, g.activeTabId)
							: g.tabHistory);
					return { ...g, tabs: result.tabs, activeTabId: newActiveId, tabHistory };
				}),
			};
		})
	);
}

// ── Tab actions (operate on the active group by default) ────────

export function reorderTabs(oldIndex: number, newIndex: number, groupId?: string): void {
	updateGroupTabs(groupId, (tabs) => {
		const reordered = [...tabs];
		const [moved] = reordered.splice(oldIndex, 1);
		reordered.splice(newIndex, 0, moved);
		return { tabs: reordered };
	});
}

export function openFileTab(filePath: string, targetGroupId?: string): void {
	const ws = get(activeWorkspace);
	if (!ws) return;

	const gid = targetGroupId ?? ws.activeGroupId;
	const group = ws.groups.find((g) => g.id === gid);
	if (!group) return;

	// Reuse existing tab within this group
	const existing = group.tabs.find((t) => t.type === 'file' && t.filePath === filePath);
	if (existing) {
		setActiveTab(existing.id, gid);
		return;
	}

	const name = filePath.split('/').pop() || filePath;
	const newTab: Tab = {
		id: nextId(),
		type: 'file',
		label: name,
		filePath,
	};

	updateGroupTabs(gid, (tabs) => ({
		tabs: [...tabs, newTab],
		activeTabId: newTab.id,
	}));
}

export function openUntitledFileTab(targetGroupId?: string): void {
	// Find the lowest unused number across ALL groups
	const allTabs = get(workspaces).flatMap((ws) => ws.groups.flatMap((g) => g.tabs));
	const usedNumbers = new Set(
		allTabs
			.filter((t) => t.filePath?.startsWith('untitled:Untitled-'))
			.map((t) => parseInt(t.filePath!.replace('untitled:Untitled-', ''), 10))
			.filter((n) => !isNaN(n))
	);
	let n = 1;
	while (usedNumbers.has(n)) n++;

	const label = `Untitled-${n}`;
	const newTab: Tab = {
		id: nextId(),
		type: 'file',
		label,
		filePath: `untitled:${label}`,
		unsaved: true,
	};

	updateGroupTabs(targetGroupId, (tabs) => ({
		tabs: [...tabs, newTab],
		activeTabId: newTab.id,
	}));
}

export async function openTerminalTab(targetGroupId?: string): Promise<void> {
	const ws = get(activeWorkspace);
	if (!ws) return;

	try {
		const data = await createSession(ws.path);

		const newTab: Tab = {
			id: nextId(),
			type: 'terminal',
			label: 'Terminal',
			sessionId: data.session_id,
		};

		updateGroupTabs(targetGroupId, (tabs) => ({
			tabs: [...tabs, newTab],
			activeTabId: newTab.id,
		}));
	} catch (e) {
		console.error('Failed to create terminal:', e);
	}
}

export function openPreviewTab(port: number, targetGroupId?: string): void {
	const ws = get(activeWorkspace);
	if (!ws) return;

	const gid = targetGroupId ?? ws.activeGroupId;
	const group = ws.groups.find((g) => g.id === gid);
	if (!group) return;

	// Reuse existing tab within this group
	const existing = group.tabs.find((t) => t.type === 'preview' && t.port === port);
	if (existing) {
		setActiveTab(existing.id, gid);
		return;
	}

	const newTab: Tab = {
		id: nextId(),
		type: 'preview',
		label: `localhost:${port}`,
		port,
	};

	updateGroupTabs(gid, (tabs) => ({
		tabs: [...tabs, newTab],
		activeTabId: newTab.id,
	}));
}

export function openChatTab(chatId?: string, targetGroupId?: string): void {
	const ws = get(activeWorkspace);
	if (!ws) return;

	const gid = targetGroupId ?? ws.activeGroupId;
	const group = ws.groups.find((g) => g.id === gid);
	if (!group) return;

	// If chatId provided, reuse existing tab
	if (chatId) {
		const existing = group.tabs.find((t) => t.type === 'chat' && t.path === chatId);
		if (existing) {
			setActiveTab(existing.id, gid);
			return;
		}
	}

	const newTab: Tab = {
		id: nextId(),
		type: 'chat',
		label: 'New Chat',
		path: chatId || `new-${Date.now()}`,
	};

	updateGroupTabs(gid, (tabs) => ({
		tabs: [...tabs, newTab],
		activeTabId: newTab.id,
	}));
}

export function closeTab(tabId: string, groupId?: string): void {
	const ws = get(activeWorkspace);
	if (!ws) return;

	// Find the group containing this tab
	const gid = groupId ?? ws.groups.find((g) => g.tabs.some((t) => t.id === tabId))?.id ?? ws.activeGroupId;
	const group = ws.groups.find((g) => g.id === gid);
	if (!group) return;

	const tab = group.tabs.find((t) => t.id === tabId);
	if (!tab || tab.permanent) return;

	if (tab.type === 'terminal' && tab.sessionId) {
		deleteSession(tab.sessionId);
	}

	const wsId = get(activeWorkspaceId);
	if (!wsId) return;

	workspaces.update((list) =>
		list.map((w) => {
			if (w.id !== wsId) return w;

			let newGroups = w.groups.map((g) => {
				if (g.id !== gid) return g;
				const newTabs = g.tabs.filter((t) => t.id !== tabId);
				const tabIdSet = new Set(newTabs.map((t) => t.id));
				let newActiveId = g.activeTabId;

				if (newActiveId === tabId) {
					// Walk back through MRU history
					const history = g.tabHistory ?? [];
					let found = false;
					for (let i = history.length - 1; i >= 0; i--) {
						if (tabIdSet.has(history[i])) {
							newActiveId = history[i];
							found = true;
							break;
						}
					}
					if (!found) {
						const idx = g.tabs.findIndex((t) => t.id === tabId);
						newActiveId = newTabs[Math.max(0, idx - 1)]?.id ?? newTabs[0]?.id ?? '';
					}
				}
				const tabHistory = (g.tabHistory ?? []).filter((id) => id !== tabId);
				return { ...g, tabs: newTabs, activeTabId: newActiveId, tabHistory };
			});

			// Remove empty non-primary groups (groups with no tabs collapse)
			newGroups = newGroups.filter((g) => g.tabs.length > 0);
			if (newGroups.length === 0) {
				newGroups = [createDefaultGroup()];
			}

			// If active group was removed, switch to first remaining
			const activeGroupStillExists = newGroups.some((g) => g.id === w.activeGroupId);

			return {
				...w,
				groups: newGroups,
				activeGroupId: activeGroupStillExists ? w.activeGroupId : newGroups[0].id,
			};
		})
	);
}

export function setActiveTab(tabId: string, groupId?: string): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;

	workspaces.update((list) =>
		list.map((ws) => {
			if (ws.id !== wsId) return ws;
			const gid = groupId ?? ws.activeGroupId;
			return {
				...ws,
				activeGroupId: gid, // Clicking a tab in a group focuses that group
				groups: ws.groups.map((g) => {
					if (g.id !== gid) return g;
					if (g.activeTabId === tabId) return g;
					return {
						...g,
						activeTabId: tabId,
						tabHistory: pushTabHistory(g, g.activeTabId),
					};
				}),
			};
		})
	);
}

export function setActiveGroup(groupId: string): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;
	workspaces.update((list) =>
		list.map((ws) => (ws.id === wsId ? { ...ws, activeGroupId: groupId } : ws))
	);
}

export function setFileBrowserCwd(cwd: string): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;
	workspaces.update((list) =>
		list.map((ws) => (ws.id === wsId ? { ...ws, fileBrowserCwd: cwd } : ws))
	);
}

export function markTabUnsaved(tabId: string, unsaved: boolean): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;
	workspaces.update((list) =>
		list.map((ws) => {
			if (ws.id !== wsId) return ws;
			return {
				...ws,
				groups: ws.groups.map((g) => ({
					...g,
					tabs: g.tabs.map((t) => (t.id === tabId ? { ...t, unsaved } : t)),
				})),
			};
		})
	);
}

export function updateTabFilePath(tabId: string, newPath: string): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;
	const name = newPath.split('/').pop() || newPath;
	workspaces.update((list) =>
		list.map((ws) => {
			if (ws.id !== wsId) return ws;
			return {
				...ws,
				groups: ws.groups.map((g) => ({
					...g,
					tabs: g.tabs.map((t) =>
						t.id === tabId ? { ...t, filePath: newPath, label: name, unsaved: false } : t
					),
				})),
			};
		})
	);
}

// ── Split / Editor Group actions ────────────────────────────────

/** Open a file in a new split group (creates the group if needed) */
export function openInSplit(filePath: string, direction?: SplitDirection): void {
	const ws = get(activeWorkspace);
	if (!ws) return;

	const wsId = get(activeWorkspaceId)!;
	const dir = direction ?? ws.splitDirection ?? 'horizontal';

	// If there's already a second group, open in it
	if (ws.groups.length > 1) {
		const otherGroup = ws.groups.find((g) => g.id !== ws.activeGroupId);
		if (otherGroup) {
			openFileTab(filePath, otherGroup.id);
			return;
		}
	}

	// Create a new group with this file
	const name = filePath.split('/').pop() || filePath;
	const newTab: Tab = { id: nextId(), type: 'file', label: name, filePath };
	const newGroup: EditorGroup = {
		id: nextId(),
		tabs: [newTab],
		activeTabId: newTab.id,
	};

	workspaces.update((list) =>
		list.map((w) => {
			if (w.id !== wsId) return w;
			return {
				...w,
				groups: [...w.groups, newGroup],
				activeGroupId: newGroup.id,
				splitDirection: dir,
				splitRatio: w.splitRatio ?? 0.5,
			};
		})
	);
}

/** Split the current active tab into a new group */
export function splitCurrentTab(direction?: SplitDirection): void {
	const ws = get(activeWorkspace);
	if (!ws) return;
	const group = ws.groups.find((g) => g.id === ws.activeGroupId);
	if (!group) return;
	const tab = group.tabs.find((t) => t.id === group.activeTabId);
	if (!tab) return;

	const wsId = get(activeWorkspaceId)!;
	const dir = direction ?? ws.splitDirection ?? 'horizontal';

	// If already split, focus the other group
	if (ws.groups.length > 1) {
		const otherGroup = ws.groups.find((g) => g.id !== ws.activeGroupId);
		if (otherGroup) {
			setActiveGroup(otherGroup.id);
			return;
		}
	}

	// Copy the tab into a new group
	const newTab: Tab = { ...tab, id: nextId(), permanent: false };
	const newGroup: EditorGroup = {
		id: nextId(),
		tabs: [newTab],
		activeTabId: newTab.id,
	};

	workspaces.update((list) =>
		list.map((w) => {
			if (w.id !== wsId) return w;
			return {
				...w,
				groups: [...w.groups, newGroup],
				activeGroupId: newGroup.id,
				splitDirection: dir,
				splitRatio: w.splitRatio ?? 0.5,
			};
		})
	);
}

/** Close an entire editor group */
export function closeGroup(groupId: string): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;

	workspaces.update((list) =>
		list.map((ws) => {
			if (ws.id !== wsId) return ws;

			// Clean up terminal sessions in this group
			const group = ws.groups.find((g) => g.id === groupId);
			if (group) {
				group.tabs.forEach((t) => {
					if (t.type === 'terminal' && t.sessionId) deleteSession(t.sessionId);
				});
			}

			let newGroups = ws.groups.filter((g) => g.id !== groupId);
			if (newGroups.length === 0) {
				newGroups = [createDefaultGroup()];
			}
			const activeGroupStillExists = newGroups.some((g) => g.id === ws.activeGroupId);
			return {
				...ws,
				groups: newGroups,
				activeGroupId: activeGroupStillExists ? ws.activeGroupId : newGroups[0].id,
			};
		})
	);
}

/** Move a tab from one group to another */
export function moveTabToGroup(tabId: string, fromGroupId: string, toGroupId: string): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;

	workspaces.update((list) =>
		list.map((ws) => {
			if (ws.id !== wsId) return ws;
			const fromGroup = ws.groups.find((g) => g.id === fromGroupId);
			if (!fromGroup) return ws;
			const tab = fromGroup.tabs.find((t) => t.id === tabId);
			if (!tab) return ws;

			let newGroups = ws.groups.map((g) => {
				if (g.id === fromGroupId) {
					const newTabs = g.tabs.filter((t) => t.id !== tabId);
					const newActiveId = g.activeTabId === tabId
						? (newTabs[0]?.id ?? 'files')
						: g.activeTabId;
					return { ...g, tabs: newTabs, activeTabId: newActiveId };
				}
				if (g.id === toGroupId) {
					return { ...g, tabs: [...g.tabs, tab], activeTabId: tab.id };
				}
				return g;
			});

			// Remove empty non-primary groups
			newGroups = newGroups.filter((g) => g.tabs.length > 0);
			if (newGroups.length === 0) newGroups = [createDefaultGroup()];

			const activeGroupStillExists = newGroups.some((g) => g.id === ws.activeGroupId);
			return {
				...ws,
				groups: newGroups,
				activeGroupId: activeGroupStillExists ? ws.activeGroupId : newGroups[0].id,
			};
		})
	);
}

export function setSplitDirection(direction: SplitDirection): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;
	workspaces.update((list) =>
		list.map((ws) => (ws.id === wsId ? { ...ws, splitDirection: direction } : ws))
	);
}

export function setSplitRatio(ratio: number): void {
	const wsId = get(activeWorkspaceId);
	if (!wsId) return;
	workspaces.update((list) =>
		list.map((ws) => (ws.id === wsId ? { ...ws, splitRatio: Math.max(0.2, Math.min(0.8, ratio)) } : ws))
	);
}
