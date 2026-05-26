import tippy, { type Props as TippyProps } from 'tippy.js';
import 'tippy.js/dist/tippy.css';

/**
 * Svelte action for tippy.js tooltips.
 * Usage: <button use:tooltip={'New terminal'}>
 *    or: <button use:tooltip={{ content: 'New terminal', placement: 'bottom' }}>
 */
export function tooltip(node: HTMLElement, params: string | Partial<TippyProps>) {
	const opts: Partial<TippyProps> =
		typeof params === 'string' ? { content: params } : params;

	const instance = tippy(node, {
		arrow: false,
		delay: [400, 0],
		duration: [100, 75],
		placement: 'bottom',
		theme: 'cptr',
		touch: false,
		...opts,
	});

	return {
		update(newParams: string | Partial<TippyProps>) {
			const newOpts = typeof newParams === 'string' ? { content: newParams } : newParams;
			instance.setProps(newOpts);
		},
		destroy() {
			instance.destroy();
		},
	};
}
