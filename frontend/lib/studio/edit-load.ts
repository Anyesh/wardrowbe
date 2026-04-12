export type EditLoadPhase =
  | 'loading'
  | 'missing'
  | 'error'
  | 'wornImmutable'
  | 'ready';

export interface EditLoadInputs {
  isLoading: boolean;
  isError: boolean;
  errorStatus: number | null;
  hasData: boolean;
  isWorn: boolean;
  editLoaded: boolean;
}

export function computeEditLoadPhase(input: EditLoadInputs): EditLoadPhase {
  if (input.editLoaded) return 'ready';
  if (input.isError) {
    return input.errorStatus === 404 ? 'missing' : 'error';
  }
  if (input.isLoading) return 'loading';
  if (input.hasData) {
    if (input.isWorn) return 'wornImmutable';
    return 'loading';
  }
  return 'missing';
}
