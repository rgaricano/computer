/**
 * State API — user state, welcome/system info.
 */
import { fetchHandler, fetchJSON, jsonBody } from '$lib/apis';

export const getState = () => fetchJSON<Record<string, unknown>>('/api/state');

export const saveState = (data: Record<string, unknown>) =>
	fetchHandler('/api/state', { ...jsonBody(data), method: 'PUT' });

export const getWelcome = () => fetchJSON<Record<string, unknown>>('/api/state/welcome');
