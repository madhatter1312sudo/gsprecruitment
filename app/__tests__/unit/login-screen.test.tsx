import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import LoginScreen from '../../app/(auth)/login';
import * as api from '../../lib/api';
import { useAuthStore } from '../../lib/auth';
import { useLanguageStore } from '../../lib/i18n';

jest.mock('../../lib/api', () => {
  const actual = jest.requireActual('../../lib/api');
  return { ...actual, login: jest.fn() };
});

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LoginScreen />
    </QueryClientProvider>,
  );
}

describe('LoginScreen', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await useAuthStore.getState().logout();
    useLanguageStore.getState().setLang('en');
  });

  it('shows a validation error for an invalid email without calling the API', async () => {
    await renderLogin();
    await fireEvent.changeText(screen.getAllByDisplayValue('')[0], 'not-an-email');
    await fireEvent.press(screen.getByText('Log in'));
    expect(screen.getByText('Enter a valid email address.')).toBeTruthy();
    expect(api.login).not.toHaveBeenCalled();
  });

  it('shows a validation error when the password is empty', async () => {
    await renderLogin();
    const inputs = screen.getAllByDisplayValue('');
    await fireEvent.changeText(inputs[0], 'jane@example.com');
    await fireEvent.press(screen.getByText('Log in'));
    expect(screen.getByText('At least 8 characters, with an uppercase letter, lowercase letter and digit.')).toBeTruthy();
    expect(api.login).not.toHaveBeenCalled();
  });

  it('calls login and stores the session on valid submit', async () => {
    (api.login as jest.Mock).mockResolvedValue({
      access_token: 'tok-123',
      token_type: 'bearer',
      user: { id: 1, email: 'jane@example.com', full_name: 'Jane Doe', role: 'candidate', is_verified: true },
    });
    await renderLogin();
    const inputs = screen.getAllByDisplayValue('');
    await fireEvent.changeText(inputs[0], 'jane@example.com');
    await fireEvent.changeText(inputs[1], 'Sup3rSecret');
    await fireEvent.press(screen.getByText('Log in'));

    await waitFor(() => expect(api.login).toHaveBeenCalledWith('jane@example.com', 'Sup3rSecret'));
    await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(true));
    expect(useAuthStore.getState().accessToken).toBe('tok-123');
  });

  it('shows the incorrect-credentials message on a 401', async () => {
    (api.login as jest.Mock).mockRejectedValue(new api.ApiError(401, 'Unauthorized'));
    await renderLogin();
    const inputs = screen.getAllByDisplayValue('');
    await fireEvent.changeText(inputs[0], 'jane@example.com');
    await fireEvent.changeText(inputs[1], 'wrongpassword1A');
    await fireEvent.press(screen.getByText('Log in'));

    await waitFor(() => expect(screen.getByText('Incorrect email or password.')).toBeTruthy());
  });
});
