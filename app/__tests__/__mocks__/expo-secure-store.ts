/**
 * Manual mock for `expo-secure-store` (see jest.config.js
 * `moduleNameMapper`) — an in-memory Map standing in for the OS keychain,
 * wrapped in jest.fn() so tests can assert on calls or override behavior
 * per-test with mockImplementation/mockResolvedValue.
 */
const store = new Map<string, string>();

export const getItemAsync = jest.fn(async (key: string): Promise<string | null> => {
  return store.has(key) ? store.get(key)! : null;
});

export const setItemAsync = jest.fn(async (key: string, value: string): Promise<void> => {
  store.set(key, value);
});

export const deleteItemAsync = jest.fn(async (key: string): Promise<void> => {
  store.delete(key);
});

export function __reset() {
  store.clear();
  getItemAsync.mockClear();
  setItemAsync.mockClear();
  deleteItemAsync.mockClear();
}
