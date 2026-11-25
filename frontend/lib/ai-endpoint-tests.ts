import type { AIEndpoint } from '@/lib/types';

// What a connection test ran with: its result describes that server and those credentials only.
export interface TestedWith {
  url: string;
  apiKey?: string;
}

// Whether a test result still describes the endpoint as it is now in the form. A result is
// dropped once the URL or the key changes, including after "Remove key". A key typed, tested
// and then saved comes back as "saved", which is still the key the test ran with.
export function testStillApplies(test: TestedWith, endpoint: AIEndpoint): boolean {
  if (test.url !== endpoint.url) return false;
  if (test.apiKey === endpoint.api_key) return true;
  return !!test.apiKey && endpoint.api_key === undefined && !!endpoint.has_api_key;
}

// Results kept by list position, moved with their endpoints; a null new index drops one.
export function moveByIndex<T>(
  results: Record<number, T>,
  newIndex: (oldIndex: number) => number | null,
): Record<number, T> {
  const moved: Record<number, T> = {};
  for (const [oldIndex, result] of Object.entries(results)) {
    const target = newIndex(Number(oldIndex));
    if (target !== null) moved[target] = result;
  }
  return moved;
}
