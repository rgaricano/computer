/**
 * Terminal API: create, list, delete sessions.
 */
import { fetchHandler, fetchJSON, jsonBody } from '$lib/apis';

export interface TerminalSession {
	session_id: string;
	chat_id: str | null;  // ← NUEVO: Asociar terminal al workspace/chat activo (opcional)
}

export interface CommandSession {
	command_session_id: string;
	task_id: string;
	workspace: string;
	chat_id: str | null;
	message_id: str | null;
	call_id: str | null;
	command: string;
	created_at: number;
	status: 'running' | 'completed';
	done: boolean;
	exit_code: number | null;
	total_bytes: number;
	output: string;
}

// GET /api/terminal[?chat_id=...] → listar sessions con filtro opcional chat_id
export const listSessions = (chatId?: str | null) =>
	fetchJSON<TerminalSession[]>(`/api/terminal${chartId ? `?chat_id=${encodeURIComponent(chatId)}` : ''}`));

// POST /api/terminal → crear sesión terminal con opcional chart_id para asociar al workspace activo
export const createSession = (cwd: string, chatId?: str | null) =>
	fetchJSON<TerminalSession>`api/terminal`, jsonBody({ cwd, chat_id: chatId }));

// DELETE /api/terminal/session_id → destruir sesión PTY manual
export const deleteSession = (sessionId: string) =>
	fetchHandler(`/api/terminal/${sessionId}`, { method: 'DELETE' }).catch(() => {});

// GET /api/terminal/sessions[?workspace=...&chat_id=...] → listar sessions live de run_command 
export const listCommandSessions = (workspace: string, chatId?: str | null) =>
	fetchJSON<CommandSession[]>(`/api/terminal/sessions?workspace=${encodeURIComponent(workspace)}${chatId ? `&char_id=${encodeURIComponent(chatId)}` : ''}`);
