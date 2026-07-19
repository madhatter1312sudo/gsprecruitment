import * as SecureStore from 'expo-secure-store';
import { useAuthStore, getAuthState, type AuthUser } from '../../lib/auth';

const user: AuthUser = { id: 1, email: 'jane@example.com', full_name: 'Jane Doe', role: 'candidate', is_verified: true };

describe('useAuthStore', () => {
  beforeEach(async () => {
    // Reset store + secure-store mock state between tests.
    await useAuthStore.getState().logout();
    jest.clearAllMocks();
  });

  it('starts logged out and unhydrated', () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
  });

  it('setSession logs the user in and persists to SecureStore', async () => {
    await useAuthStore.getState().setSession('token-123', user);
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe('token-123');
    expect(state.user).toEqual(user);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('gsp_access_token', 'token-123');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('gsp_user', JSON.stringify(user));
  });

  it('logout clears the session and SecureStore', async () => {
    await useAuthStore.getState().setSession('token-123', user);
    await useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('gsp_access_token');
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('gsp_user');
  });

  it('updateUser patches the user without touching the token', async () => {
    await useAuthStore.getState().setSession('token-123', user);
    const updated: AuthUser = { ...user, full_name: 'Jane Smith' };
    useAuthStore.getState().updateUser(updated);
    expect(useAuthStore.getState().user).toEqual(updated);
    expect(useAuthStore.getState().accessToken).toBe('token-123');
  });

  it('hydrate restores a persisted session from SecureStore', async () => {
    // hydrate() reads the token then the user key via Promise.all (in that
    // argument order) — queue one-off responses so this doesn't leak into
    // other tests.
    (SecureStore.getItemAsync as jest.Mock)
      .mockImplementationOnce(async () => 'restored-token')
      .mockImplementationOnce(async () => JSON.stringify(user));
    await useAuthStore.getState().hydrate();
    const state = useAuthStore.getState();
    expect(state.hydrated).toBe(true);
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe('restored-token');
    expect(state.user).toEqual(user);
  });

  it('hydrate leaves the user logged out when nothing is persisted', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockImplementationOnce(async () => null).mockImplementationOnce(async () => null);
    await useAuthStore.getState().hydrate();
    const state = useAuthStore.getState();
    expect(state.hydrated).toBe(true);
    expect(state.isAuthenticated).toBe(false);
  });

  it('getAuthState exposes the same state as the hook store (used by lib/api.ts)', async () => {
    await useAuthStore.getState().setSession('token-abc', user);
    expect(getAuthState().accessToken).toBe('token-abc');
    expect(getAuthState().user).toEqual(user);
  });
});
