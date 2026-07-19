import { isValidEmail, isStrongPassword } from '../../lib/validation';

describe('isValidEmail', () => {
  it('accepts well-formed addresses', () => {
    expect(isValidEmail('name@example.com')).toBe(true);
    expect(isValidEmail('  name@example.com  ')).toBe(true);
    expect(isValidEmail('first.last+tag@sub.example.co.uk')).toBe(true);
  });

  it('rejects malformed addresses', () => {
    expect(isValidEmail('')).toBe(false);
    expect(isValidEmail('not-an-email')).toBe(false);
    expect(isValidEmail('missing@domain')).toBe(false);
    expect(isValidEmail('@missing-local.com')).toBe(false);
    expect(isValidEmail('spaces in@email.com')).toBe(false);
  });
});

describe('isStrongPassword', () => {
  it('accepts a password with 8+ chars, upper, lower and digit', () => {
    expect(isStrongPassword('Abcdefg1')).toBe(true);
    expect(isStrongPassword('Sup3rSecret')).toBe(true);
  });

  it('rejects passwords missing a required class or length', () => {
    expect(isStrongPassword('short1A')).toBe(false); // < 8 chars
    expect(isStrongPassword('alllowercase1')).toBe(false); // no uppercase
    expect(isStrongPassword('ALLUPPERCASE1')).toBe(false); // no lowercase
    expect(isStrongPassword('NoDigitsHere')).toBe(false); // no digit
    expect(isStrongPassword('')).toBe(false);
  });
});
