import { canonicalItemOrder } from '@/lib/studio/canonical-order';

export interface StudioItem {
  id: string;
  type: string;
  name: string | null;
  thumbnail_url?: string | null;
  image_url?: string | null;
  primary_color?: string | null;
}

export interface StudioEditorState {
  items: StudioItem[];
  name: string;
  occasion: string | null;
  isDirty: boolean;
  lastModified: number;
}

export const INITIAL_STUDIO_STATE: StudioEditorState = {
  items: [],
  name: '',
  occasion: null,
  isDirty: false,
  lastModified: 0,
};

export type StudioAction =
  | { type: 'ADD_ITEM'; item: StudioItem }
  | { type: 'REMOVE_ITEM'; itemId: string }
  | { type: 'TOGGLE_ITEM'; item: StudioItem }
  | { type: 'SET_NAME'; name: string }
  | { type: 'SET_OCCASION'; occasion: string }
  | { type: 'REPLACE_CANVAS'; items: StudioItem[] }
  | { type: 'LOAD'; state: Partial<StudioEditorState> }
  | { type: 'RESET' };

function touch(state: StudioEditorState): StudioEditorState {
  return {
    ...state,
    isDirty: true,
    lastModified: Date.now(),
  };
}

export function studioReducer(
  state: StudioEditorState,
  action: StudioAction
): StudioEditorState {
  switch (action.type) {
    case 'ADD_ITEM': {
      if (state.items.some((i) => i.id === action.item.id)) return state;
      return touch({
        ...state,
        items: canonicalItemOrder([...state.items, action.item]),
      });
    }
    case 'REMOVE_ITEM': {
      const next = state.items.filter((i) => i.id !== action.itemId);
      if (next.length === state.items.length) return state;
      return touch({ ...state, items: next });
    }
    case 'TOGGLE_ITEM': {
      if (state.items.some((i) => i.id === action.item.id)) {
        return touch({
          ...state,
          items: state.items.filter((i) => i.id !== action.item.id),
        });
      }
      return touch({
        ...state,
        items: canonicalItemOrder([...state.items, action.item]),
      });
    }
    case 'SET_NAME': {
      if (state.name === action.name) return state;
      return touch({ ...state, name: action.name });
    }
    case 'SET_OCCASION': {
      if (state.occasion === action.occasion) return state;
      return touch({ ...state, occasion: action.occasion });
    }
    case 'REPLACE_CANVAS': {
      return touch({
        ...state,
        items: canonicalItemOrder(action.items),
      });
    }
    case 'LOAD': {
      return {
        ...state,
        ...action.state,
        isDirty: false,
      };
    }
    case 'RESET':
      return { ...INITIAL_STUDIO_STATE };
    default:
      return state;
  }
}
