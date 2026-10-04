// @vitest-environment node
import { createServer } from 'node:http';
import { Issuer } from 'openid-client';
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

  async function captureTokenRequest(supportedMethods: string[]) {
    let authorization: string | undefined;
    let body = '';
    const server = createServer((request, response) => {
      authorization = request.headers.authorization;
      request.setEncoding('utf8');
      request.on('data', (chunk: string) => { body += chunk; });
      request.on('end', () => {
        response.writeHead(200, { 'content-type': 'application/json' });
        response.end(JSON.stringify({ access_token: 'test-token', token_type: 'Bearer' }));
      });
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));

    try {
      const address = server.address();
      if (!address || typeof address === 'string') throw new Error('Missing test server port');
      const endpoint = `http://127.0.0.1:${address.port}/token`;
      const issuer = new Issuer({
        issuer: `http://127.0.0.1:${address.port}`,
        token_endpoint: endpoint,
        token_endpoint_auth_methods_supported: supportedMethods,
      });
      const provider = await oidcProvider() as { client?: { token_endpoint_auth_method?: 'client_secret_basic' | 'client_secret_post' } };
      const client = new issuer.Client({
        client_id: 'wardrowbe',
        client_secret: 'test-secret',
        ...provider.client,
      });
      await client.grant({ grant_type: 'client_credentials' });
      return { authorization, form: new URLSearchParams(body) };
    } finally {
      await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
    }
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

  it.each(['client_secret_basic', 'client_secret_post'] as const)(
    'sends credentials using %s on the token request', async (method) => {
      process.env.OIDC_ISSUER_URL = 'https://auth.example.com';
      process.env.OIDC_TOKEN_ENDPOINT_AUTH_METHOD = method;

      const request = await captureTokenRequest(['client_secret_basic', 'client_secret_post']);
      if (method === 'client_secret_basic') {
        expect(request.authorization).toBe(`Basic ${Buffer.from('wardrowbe:test-secret').toString('base64')}`);
        expect(request.form.has('client_secret')).toBe(false);
      } else {
        expect(request.authorization).toBeUndefined();
        expect(request.form.get('client_id')).toBe('wardrowbe');
        expect(request.form.get('client_secret')).toBe('test-secret');
      }
    },
  );

  it('uses provider discovery to select Post when no override is set', async () => {
    process.env.OIDC_ISSUER_URL = 'https://auth.example.com';
    const request = await captureTokenRequest(['client_secret_post']);
    expect(request.authorization).toBeUndefined();
    expect(request.form.get('client_secret')).toBe('test-secret');
  });
});
