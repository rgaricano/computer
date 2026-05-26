<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Terminal } from '@xterm/xterm';
	import { FitAddon } from '@xterm/addon-fit';
	import { WebglAddon } from '@xterm/addon-webgl';

	// Binary WebSocket protocol (industry standard, same as ttyd/GoTTY):
	// Byte 0 = message type, rest = payload.
	// Client → Server:  0x00 + raw input bytes  |  0x02 + JSON resize
	// Server → Client:  raw PTY output bytes (no prefix needed)
	const MSG_INPUT  = 0;
	const MSG_RESIZE = 2;

	const textEncoder = new TextEncoder();

	interface Props {
		sessionId: string;
	}

	let { sessionId }: Props = $props();

	let containerEl: HTMLDivElement | undefined = $state();
	let term: Terminal | null = null;
	let fitAddon: FitAddon | null = null;
	let ws: WebSocket | null = null;
	let resizeObserver: ResizeObserver | null = null;
	let resizeTimeout: ReturnType<typeof setTimeout> | null = null;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let destroyed = false;
	let lastSentCols = 0;
	let lastSentRows = 0;

	function getWsUrl(sid: string): string {
		const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		return `${proto}//${window.location.host}/api/terminal/${sid}/ws`;
	}

	function doFit() {
		if (!fitAddon || !term || !containerEl) return;
		const rect = containerEl.getBoundingClientRect();
		if (rect.width === 0 || rect.height === 0) return;
		try {
			fitAddon.fit();
			// Do NOT scroll after fit — rich CLI apps (htop, vim, Claude Code)
			// manage their own cursor/viewport after SIGWINCH. Forcing scroll
			// interferes with their rendering.
		} catch {
			// FitAddon can throw if terminal not properly attached
		}
	}

	function debouncedFit() {
		if (resizeTimeout) clearTimeout(resizeTimeout);
		// 350ms debounce — long enough to outlast the mobile keyboard
		// animation so we only refit ONCE after it fully settles.
		resizeTimeout = setTimeout(() => doFit(), 350);
	}

	function isDarkMode(): boolean {
		return document.documentElement.classList.contains('dark');
	}

	const darkTheme = {
		background: '#000000',
		foreground: '#e0e0e0',
		cursor: '#e0e0e0',
		cursorAccent: '#000000',
		selectionBackground: 'rgba(255, 255, 255, 0.2)',
	};

	const lightTheme = {
		background: '#ffffff',
		foreground: '#1a1a1a',
		cursor: '#1a1a1a',
		cursorAccent: '#ffffff',
		selectionBackground: 'rgba(0, 0, 0, 0.15)',
	};

	onMount(() => {
		if (!containerEl) return;

		term = new Terminal({
			cursorBlink: true,
			cursorStyle: 'bar',
			fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, monospace',
			fontSize: 13,
			lineHeight: 1.3,
			scrollback: 10000,
			macOptionClickForceSelection: true,
			theme: isDarkMode() ? darkTheme : lightTheme,
		});

		// Watch for theme changes
		const observer = new MutationObserver(() => {
			if (term) {
				term.options.theme = isDarkMode() ? darkTheme : lightTheme;
			}
		});
		observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

		// Send input to PTY via WebSocket (binary prefix protocol)
		function sendInput(data: string) {
			if (ws?.readyState === WebSocket.OPEN) {
				const encoded = textEncoder.encode(data);
				const buf = new Uint8Array(1 + encoded.length);
				buf[0] = MSG_INPUT;
				buf.set(encoded, 1);
				ws.send(buf.buffer);
			}
		}

		function sendResize(cols: number, rows: number) {
			if (ws?.readyState === WebSocket.OPEN) {
				const payload = textEncoder.encode(JSON.stringify({ cols, rows }));
				const buf = new Uint8Array(1 + payload.length);
				buf[0] = MSG_RESIZE;
				buf.set(payload, 1);
				ws.send(buf.buffer);
			}
		}

		// Handle macOS key combos that need special escape sequences
		term.attachCustomKeyEventHandler((e: KeyboardEvent) => {
			if (e.type !== 'keydown') return true;

			// Cmd+Arrow: line navigation
			if (e.metaKey) {
				if (e.key === 'ArrowLeft') {
					sendInput('\x01'); // Ctrl-A: beginning of line
					return false;
				}
				if (e.key === 'ArrowRight') {
					sendInput('\x05'); // Ctrl-E: end of line
					return false;
				}
			}

			// Option+Arrow: word navigation
			if (e.altKey) {
				if (e.key === 'ArrowLeft') {
					sendInput('\x1bb'); // ESC-b: backward word
					return false;
				}
				if (e.key === 'ArrowRight') {
					sendInput('\x1bf'); // ESC-f: forward word
					return false;
				}
				if (e.key === 'Backspace') {
					sendInput('\x17'); // Ctrl-W: delete word backward
					return false;
				}
			}

			return true;
		});

		fitAddon = new FitAddon();
		term.loadAddon(fitAddon);
		term.open(containerEl);

		// GPU-accelerated rendering — 2-5x faster than canvas 2D.
		// Falls back to canvas if WebGL is unavailable.
		try {
			const webgl = new WebglAddon();
			webgl.onContextLoss(() => webgl.dispose());
			term.loadAddon(webgl);
		} catch {
			// WebGL not supported, canvas fallback is fine
		}

		// Register input/resize handlers ONCE — not per WebSocket connection.
		// This prevents duplicate SIGWINCH signals that cause rich CLI apps
		// (e.g. Claude Code, htop) to render content twice.
		term.onData((data: string) => {
			sendInput(data);
		});

		term.onResize(({ cols, rows }: { cols: number; rows: number }) => {
			// Skip if dimensions haven't actually changed — prevents duplicate
			// SIGWINCH when keyboard open/close triggers multiple fit cycles.
			if (cols === lastSentCols && rows === lastSentRows) return;
			lastSentCols = cols;
			lastSentRows = rows;
			sendResize(cols, rows);
		});

		connectWebSocket();

		// ── Mobile touch scrolling ──
		// We use document-level listeners to guarantee touch events are received
		// regardless of CSS touch-action settings. Events are filtered to only
		// act when the touch originated inside this terminal container.
		// overscroll-behavior: none on html (app.css) prevents pull-to-refresh;
		// e.preventDefault() here is a secondary guard.
		let touchStartY = 0;
		let lastTouchY = 0;
		let touchAccum = 0;
		let touchingTerminal = false;
		const LINE_PX = 13 * 1.3; // fontSize * lineHeight

		function isAltBuffer(): boolean {
			try {
				return term?.buffer?.active?.type === 'alternate';
			} catch {
				return false;
			}
		}

		function onTouchStart(e: TouchEvent) {
			if (e.touches.length !== 1 || !containerEl) return;
			// Only track touches that started inside this terminal
			const target = e.target as HTMLElement;
			if (!containerEl.contains(target)) return;
			touchingTerminal = true;
			touchStartY = e.touches[0].clientY;
			lastTouchY = touchStartY;
			touchAccum = 0;
		}

		function onTouchMove(e: TouchEvent) {
			if (!touchingTerminal || !term || e.touches.length !== 1) return;
			e.preventDefault(); // block pull-to-refresh / page scroll

			const currentY = e.touches[0].clientY;
			const deltaY = lastTouchY - currentY; // positive = finger moved up = scroll down
			lastTouchY = currentY;
			touchAccum += deltaY;

			// Convert accumulated pixel delta to lines
			const lines = Math.trunc(touchAccum / LINE_PX);
			if (lines !== 0) {
				if (isAltBuffer()) {
					// TUI apps (vim, htop, Claude Code) — send arrow keys
					const seq = lines > 0 ? '\x1b[B' : '\x1b[A';
					const count = Math.abs(lines);
					for (let i = 0; i < Math.min(count, 5); i++) {
						sendInput(seq);
					}
				} else {
					// Normal buffer — scroll terminal history
					term.scrollLines(lines);
				}
				touchAccum -= lines * LINE_PX;
			}
		}

		function onTouchEnd() {
			touchingTerminal = false;
		}

		// Document-level: guaranteed to receive events regardless of
		// which child element the touch lands on (.xterm-screen, etc.)
		document.addEventListener('touchstart', onTouchStart, { passive: true });
		document.addEventListener('touchmove', onTouchMove, { passive: false });
		document.addEventListener('touchend', onTouchEnd, { passive: true });

		// Initial fit — deferred to let the container settle in the DOM
		requestAnimationFrame(() => {
			doFit();
		});

		// ResizeObserver is the SOLE trigger for refitting on container
		// size changes. No other resize listener needed — the layout
		// already handles visualViewport → container height propagation.
		resizeObserver = new ResizeObserver(() => {
			debouncedFit();
		});
		resizeObserver.observe(containerEl);

		// Listen for ShortcutBar input
		function handleShortcutInput(e: Event) {
			const data = (e as CustomEvent).detail;
			sendInput(data);
		}
		window.addEventListener('cptr:terminal-input', handleShortcutInput);

		return () => {
			window.removeEventListener('cptr:terminal-input', handleShortcutInput);
			document.removeEventListener('touchstart', onTouchStart);
			document.removeEventListener('touchmove', onTouchMove);
			document.removeEventListener('touchend', onTouchEnd);
		};
	});

	function connectWebSocket() {
		if (!term || destroyed) return;

		const url = getWsUrl(sessionId);
		console.log(`[terminal] connecting to ${url}`);
		ws = new WebSocket(url);
		ws.binaryType = 'arraybuffer';

		ws.onopen = () => {
			console.log(`[terminal] WebSocket open for ${sessionId}`);
			if (term) {
				// Send ONE resize message with current dimensions.
				// Do NOT call doFit() here — that would trigger term.onResize
				// which sends a SECOND resize message, causing rich CLI apps
				// to receive double SIGWINCH and render content twice.
				lastSentCols = term.cols;
				lastSentRows = term.rows;
				console.log(`[terminal] sending resize: ${term.cols}x${term.rows}`);
				sendResize(term.cols, term.rows);
			}
		};

		ws.onmessage = (event) => {
			// Server sends raw PTY output — write directly to terminal
			if (event.data instanceof ArrayBuffer) {
				term?.write(new Uint8Array(event.data));
			} else {
				term?.write(event.data);
			}
		};

		ws.onclose = (e) => {
			console.log(`[terminal] WebSocket closed for ${sessionId}, code=${e.code}, reason=${e.reason}`);
			if (destroyed) return;
			reconnectTimer = setTimeout(() => {
				if (!destroyed) connectWebSocket();
			}, 2000);
		};

		ws.onerror = (e) => {
			console.error(`[terminal] WebSocket error for ${sessionId}`, e);
		};

		// NOTE: term.onData and term.onResize are registered in onMount,
		// NOT here. This function can be called multiple times on reconnect
		// and we must not duplicate those handlers.
	}

	onDestroy(() => {
		destroyed = true;
		if (resizeTimeout) clearTimeout(resizeTimeout);
		if (reconnectTimer) clearTimeout(reconnectTimer);
		resizeObserver?.disconnect();
		ws?.close();
		term?.dispose();
	});
</script>

<div
	bind:this={containerEl}
	class="h-full w-full pt-1 pl-2 overflow-hidden"
></div>

<style>
	@reference "../../app.css";

	:global(.xterm) {
		height: 100%;
	}
	:global(.xterm-viewport) {
		overflow-y: auto !important;
		scrollbar-width: thin;
		scrollbar-color: rgba(75, 85, 99, 0.4) transparent;
		overscroll-behavior: contain;
	}
</style>
