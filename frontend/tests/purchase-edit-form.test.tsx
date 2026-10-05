import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ItemDetailDialog } from '@/components/item-detail-dialog';
import type { Item } from '@/lib/types';

const { updateItem, mutation } = vi.hoisted(() => ({
  updateItem: vi.fn(),
  mutation: () => ({ mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/lib/hooks/use-items', () => ({
  useUpdateItem: () => ({ mutateAsync: updateItem, isPending: false }),
  useDeleteItem: mutation,
  useReanalyzeItem: mutation,
  useRotateImage: mutation,
  useRemoveBackground: mutation,
  useRestoreOriginal: mutation,
  useReplaceItemImage: mutation,
  useLogWash: mutation,
  useAddItemImage: mutation,
  useDeleteItemImage: mutation,
  useSetPrimaryImage: mutation,
  useWashHistory: () => ({ data: undefined }),
  useItemWearStats: () => ({ data: undefined }),
  useItemWearHistory: () => ({ data: undefined }),
}));

vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingTypes: () => [{ value: 'shirt', label: 'Shirt' }],
  useClothingColors: () => [],
  useFormalityLabel: () => (value: string) => value,
  useMaterialLabel: () => (value: string) => value,
  useSubtypeLabel: () => (value: string) => value,
}));
vi.mock('@/lib/hooks/use-features', () => ({ useFeatures: () => ({ data: {} }) }));
vi.mock('@/components/generate-pairings-dialog', () => ({ GeneratePairingsDialog: () => null }));
vi.mock('@/components/color-eyedropper', () => ({ ColorEyedropper: () => null }));
vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => createElement('img', { src, alt }),
}));

const item = {
  id: 'item-1',
  user_id: 'user-1',
  type: 'shirt',
  name: 'Test shirt',
  image_path: '/shirt.jpg',
  image_url: '/shirt.jpg?token=test',
  purchase_date: '2026-03-14',
  purchase_price: '124.50',
  favorite: false,
  status: 'ready',
  ai_processed: false,
  tagging_status: 'tagged',
  tags: { colors: [], style: [], season: [] },
  colors: [],
  additional_images: [],
  wear_count: 0,
  suggestion_count: 0,
  acceptance_count: 0,
  wears_since_wash: 0,
  needs_wash: false,
  effective_wash_interval: 3,
  is_archived: false,
  created_at: '2026-03-15T00:00:00Z',
  updated_at: '2026-03-15T00:00:00Z',
} satisfies Item;

describe('purchase details in the item editor', () => {
  beforeEach(() => updateItem.mockReset().mockResolvedValue({}));

  it('omits untouched fields from PATCH but sends null for an intentional clear', async () => {
    render(<ItemDetailDialog item={item} open onOpenChange={vi.fn()} />);

    fireEvent.click(screen.getByTitle('actions.editItem'));
    fireEvent.change(screen.getByPlaceholderText('placeholders.additionalNotes'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => expect(updateItem).toHaveBeenCalledOnce());
    expect(updateItem.mock.calls[0][0].data).not.toHaveProperty('purchase_date');
    expect(updateItem.mock.calls[0][0].data).not.toHaveProperty('purchase_price');

    fireEvent.click(screen.getByTitle('actions.editItem'));
    fireEvent.change(screen.getByLabelText('date'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('amount'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => expect(updateItem).toHaveBeenCalledTimes(2));
    expect(updateItem.mock.calls[1][0].data).toMatchObject({
      purchase_date: null,
      purchase_price: null,
    });
  });
});
