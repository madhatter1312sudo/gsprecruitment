const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

/**
 * Client-side password strength check: >= 8 chars, at least one uppercase,
 * one lowercase and one digit. Note the backend itself
 * (models/schemas.py UserRegister.password) only enforces min_length=8 —
 * this is a stricter UX-level rule matching the product spec, and any
 * password that satisfies it will also satisfy the backend.
 */
export function isStrongPassword(password: string): boolean {
  if (password.length < 8) return false;
  if (!/[A-Z]/.test(password)) return false;
  if (!/[a-z]/.test(password)) return false;
  if (!/[0-9]/.test(password)) return false;
  return true;
}
