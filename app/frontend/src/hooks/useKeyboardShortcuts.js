import { useEffect } from 'react';

const DEFAULT_TARGET =
  typeof document !== 'undefined'
    ? document
    : typeof window !== 'undefined'
      ? window
      : undefined;

const isEditableTarget = (target) => {
  if (!target || typeof target !== 'object') return false;
  const element = target;
  const tag = typeof element.tagName === 'string' ? element.tagName.toUpperCase() : '';
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return true;
  if (element.isContentEditable) return true;
  if (typeof element.closest === 'function') {
    return Boolean(element.closest('[contenteditable="true"]'));
  }
  return false;
};

const normaliseKey = (key) => {
  if (!key) return '';
  if (key === ' ') return 'Space';
  if (key.length === 1) return key.toUpperCase();
  return key.charAt(0).toUpperCase() + key.slice(1);
};

const buildCombos = (event) => {
  const combos = new Set();
  const key = normaliseKey(event.key);
  const modifiers = [];
  if (event.metaKey) modifiers.push('Meta');
  if (event.ctrlKey) modifiers.push('Ctrl');
  if (event.altKey) modifiers.push('Alt');
  if (event.shiftKey) modifiers.push('Shift');

  const join = (mods) => (mods.length ? `${mods.join('+')}+${key}` : key);

  combos.add(join(modifiers));
  combos.add(key);

  if (event.metaKey && !event.ctrlKey) {
    const aliasMods = modifiers.map((mod) => (mod === 'Meta' ? 'Ctrl' : mod));
    combos.add(join(aliasMods));
  }

  return Array.from(combos).filter(Boolean);
};

const useKeyboardShortcuts = (shortcuts = {}, options = {}) => {
  const {
    preventDefault = true,
    allowInInputs = false,
    target,
  } = options;

  const eventTarget = target ?? DEFAULT_TARGET;

  useEffect(() => {
    if (!eventTarget || typeof eventTarget.addEventListener !== 'function') {
      return undefined;
    }

    const handler = (event) => {
      if (!shortcuts || typeof shortcuts !== 'object') return;

      if (!allowInInputs && isEditableTarget(event.target)) {
        return;
      }

      const combos = buildCombos(event);
      let matchedCombo;
      let shortcutHandler;

      for (const combo of combos) {
        if (typeof shortcuts[combo] === 'function') {
          matchedCombo = combo;
          shortcutHandler = shortcuts[combo];
          break;
        }
      }

      if (!shortcutHandler) {
        return;
      }

      const shouldPrevent =
        typeof preventDefault === 'function'
          ? preventDefault(event, matchedCombo)
          : preventDefault;

      if (shouldPrevent) {
        event.preventDefault();
      }

      shortcutHandler(event);
    };

    const passive = preventDefault === false;
    const listenerOptions = { passive };

    eventTarget.addEventListener('keydown', handler, listenerOptions);

    return () => {
      eventTarget.removeEventListener('keydown', handler, listenerOptions);
    };
  }, [shortcuts, eventTarget, preventDefault, allowInInputs]);
};

export default useKeyboardShortcuts;
