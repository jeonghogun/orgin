const getClipboard = () => {
  if (typeof navigator === 'undefined') {
    return null;
  }
  const { clipboard } = navigator;
  return clipboard && typeof clipboard === 'object' ? clipboard : null;
};

export const canWriteToClipboard = () => {
  const clipboard = getClipboard();
  return Boolean(clipboard && typeof clipboard.writeText === 'function');
};

export const canReadFromClipboard = () => {
  const clipboard = getClipboard();
  return Boolean(clipboard && typeof clipboard.readText === 'function');
};

export const writeTextToClipboard = async (text) => {
  const clipboard = getClipboard();
  if (!clipboard || typeof clipboard.writeText !== 'function') {
    throw new Error('Clipboard write is not supported in this browser.');
  }
  await clipboard.writeText(text);
};

export const readTextFromClipboard = async () => {
  const clipboard = getClipboard();
  if (!clipboard || typeof clipboard.readText !== 'function') {
    throw new Error('Clipboard read is not supported in this browser.');
  }
  return clipboard.readText();
};

export default {
  canWriteToClipboard,
  canReadFromClipboard,
  writeTextToClipboard,
  readTextFromClipboard,
};
