import { describe, expect, it } from 'vitest';

import { moveByIndex, testStillApplies } from '@/lib/ai-endpoint-tests';
import type { AIEndpoint } from '@/lib/types';

const VLLM = 'http://vllm.lan:8000/v1';

function endpoint(fields: Partial<AIEndpoint> = {}): AIEndpoint {
  return { name: 'vllm', url: VLLM, vision_model: null, text_model: null, enabled: true, ...fields };
}

describe('testStillApplies', () => {
  it('applies to the endpoint it ran on', () => {
    expect(testStillApplies({ url: VLLM }, endpoint())).toBe(true);
    expect(testStillApplies({ url: VLLM, apiKey: 'k' }, endpoint({ api_key: 'k' }))).toBe(true);
  });

  it('stops applying once the URL changes', () => {
    expect(testStillApplies({ url: VLLM }, endpoint({ url: 'http://elsewhere/v1' }))).toBe(false);
  });

  it('stops applying once the key changes or is removed', () => {
    expect(testStillApplies({ url: VLLM, apiKey: 'k' }, endpoint({ api_key: 'other' }))).toBe(false);
    expect(testStillApplies({ url: VLLM }, endpoint({ api_key: '', has_api_key: false }))).toBe(false);
  });

  it('still applies to a typed key once it has been saved', () => {
    expect(testStillApplies({ url: VLLM, apiKey: 'k' }, endpoint({ has_api_key: true }))).toBe(true);
    expect(testStillApplies({ url: VLLM, apiKey: 'k' }, endpoint({ has_api_key: false }))).toBe(false);
  });
});

describe('moveByIndex', () => {
  const results = { 0: 'a', 1: 'b', 2: 'c' };

  it('swaps two results', () => {
    expect(moveByIndex(results, (i) => (i === 0 ? 1 : i === 1 ? 0 : i))).toEqual({ 0: 'b', 1: 'a', 2: 'c' });
  });

  it('drops a removed result and shifts the ones after it', () => {
    expect(moveByIndex(results, (i) => (i === 1 ? null : i > 1 ? i - 1 : i))).toEqual({ 0: 'a', 1: 'c' });
  });
});
