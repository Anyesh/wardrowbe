// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('OIDC token endpoint authentication', () => {
  const originalMethod = process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD;
  const originalIssuer = process.env.OIDC_ISSUER_URL;

  beforeEach(() => {
    vi.resetModules();
    delete process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD;
  });

  afterEach(() => {
    if (originalMethod === undefined) {
      delete process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD;
    } else {
      process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD = originalMethod;
    }
    if (originalIssuer === undefined) {
      delete process.env.OIDC_ISSUER_URL;
    } else {
      process.env.OIDC_ISSUER_URL = originalIssuer;
    }
  });

  async function oidcProvider() {
    const { authOptions } = await import('@/lib/auth');
    return authOptions.providers.find((provider) => provider.id === 'oidc');
  }

  it('leaves the method unset by default for provider discovery', async () => {
    process.env.OIDC_ISSUER_URL = 'https://auth.example.com';
    expect(await oidcProvider()).not.toHaveProperty('client');
  });

  it('supports an explicit client_secret_basic override', async () => {
    process.env.OIDC_ISSUER_URL = 'https://auth.example.com';
    process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD = 'client_secret_basic';
    expect(await oidcProvider()).toMatchObject({
      client: { token_endpoint_auth_method: 'client_secret_basic' },
    });
  });

  it('supports client_secret_post when explicitly configured', async () => {
    process.env.OIDC_ISSUER_URL = 'https://auth.example.com';
    process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD = 'client_secret_post';
    expect(await oidcProvider()).toMatchObject({
      client: { token_endpoint_auth_method: 'client_secret_post' },
    });
  });

  it('rejects an unsupported authentication method', async () => {
    process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD = 'none';
    await expect(import('@/lib/auth')).rejects.toThrow(
      'OIDC_TOKEN_ENDPOINT_AUTH_METHOD must be client_secret_basic or client_secret_post',
    );
  });
});
