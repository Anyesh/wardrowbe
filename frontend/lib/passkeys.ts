import {
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser';
import { API_BASE_PATH } from '@/lib/api';

export type PasskeyFailure = 'unsupported' | 'insecure' | 'cancelled' | 'duplicate' | 'failed';

export class PasskeyCeremonyError extends Error {
  reason: PasskeyFailure;

  constructor(reason: PasskeyFailure, message?: string) {
    super(message ?? reason);
    this.reason = reason;
    this.name = 'PasskeyCeremonyError';
  }
}

// WebAuthn exists only in a secure context: https, or http on localhost.
export function passkeySupport(): 'supported' | 'insecure' | 'unsupported' {
  if (typeof window === 'undefined') return 'unsupported';
  if (!window.isSecureContext) return 'insecure';
  return browserSupportsWebAuthn() ? 'supported' : 'unsupported';
}

function ceremonyFailure(error: unknown): PasskeyCeremonyError {
  if (error instanceof PasskeyCeremonyError) return error;
  const name = error instanceof Error ? error.name : '';
  const code = (error as { code?: string } | null)?.code;
  // NotAllowedError is what browsers raise for a closed prompt, a timeout or a refused biometric.
  if (name === 'NotAllowedError' || name === 'AbortError' || code === 'ERROR_CEREMONY_ABORTED') {
    return new PasskeyCeremonyError('cancelled');
  }
  if (code === 'ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED' || name === 'InvalidStateError') {
    return new PasskeyCeremonyError('duplicate');
  }
  if (name === 'SecurityError' || code === 'ERROR_INVALID_DOMAIN' || code === 'ERROR_INVALID_RP_ID') {
    return new PasskeyCeremonyError('insecure');
  }
  return new PasskeyCeremonyError('failed', error instanceof Error ? error.message : undefined);
}

function requireSupport() {
  const support = passkeySupport();
  if (support !== 'supported') throw new PasskeyCeremonyError(support);
}

export interface PasskeyAssertion {
  flowId: string;
  credential: string;
}

// The login page has no session yet, so it calls the public endpoint directly; the assertion is
// verified server-side when NextAuth's passkey provider forwards it.
export async function getPasskeyAssertion(): Promise<PasskeyAssertion> {
  requireSupport();
  const response = await fetch(`${API_BASE_PATH}/auth/passkeys/login/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }).catch(() => {
    throw new PasskeyCeremonyError('failed');
  });
  if (!response.ok) throw new PasskeyCeremonyError('failed');
  const { flow_id: flowId, options } = (await response.json()) as {
    flow_id: string;
    options: PublicKeyCredentialRequestOptionsJSON;
  };
  try {
    const assertion = await startAuthentication({ optionsJSON: options });
    return { flowId, credential: JSON.stringify(assertion) };
  } catch (error) {
    throw ceremonyFailure(error);
  }
}

export async function createPasskeyCredential(
  options: PublicKeyCredentialCreationOptionsJSON
): Promise<Record<string, unknown>> {
  requireSupport();
  try {
    const credential = await startRegistration({ optionsJSON: options });
    return credential as unknown as Record<string, unknown>;
  } catch (error) {
    throw ceremonyFailure(error);
  }
}

// A starting label so that users rarely need to type one.
export function suggestedPasskeyName(): string {
  if (typeof navigator === 'undefined') return 'Passkey';
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return 'iPhone';
  if (/iPad/.test(ua)) return 'iPad';
  if (/Android/.test(ua)) return 'Android';
  if (/Macintosh|Mac OS X/.test(ua)) return 'Mac';
  if (/Windows/.test(ua)) return 'Windows Hello';
  if (/Linux/.test(ua)) return 'Linux';
  return 'Passkey';
}
