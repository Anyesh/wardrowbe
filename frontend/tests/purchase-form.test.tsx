import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AddItemDialog } from '@/components/add-item-dialog';

const { createItem } = vi.hoisted(() => ({ createItem: vi.fn() }));

vi.mock('@/lib/hooks/use-items', () => ({
  useCreateItem: () => ({ mutateAsync: createItem, isPending: false }),
  useBulkCreateItems: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingTypes: () => [],
  useClothingColors: () => [],
}));

vi.mock('react-dropzone', () => ({
  useDropzone: ({ onDrop }: { onDrop: (files: File[]) => void }) => ({
    getRootProps: () => ({ onClick: () => onDrop([new File(['photo'], 'shirt.jpg', { type: 'image/jpeg' })]) }),
    getInputProps: () => ({}),
    isDragActive: false,
  }),
}));

describe('single-item purchase form', () => {
  beforeEach(() => {
    createItem.mockReset().mockResolvedValue({});
  });

  it('submits the date and exact decimal string with the photo', async () => {
    render(<AddItemDialog open onOpenChange={vi.fn()} />);

    fireEvent.click(screen.getByText('dropzone'));
    await screen.findByAltText('previewAlt');
    fireEvent.change(screen.getByLabelText('date'), { target: { value: '2026-06-10' } });
    fireEvent.change(screen.getByLabelText('amount'), { target: { value: '12,50' } });
    fireEvent.click(screen.getByRole('button', { name: 'submit' }));

    await waitFor(() => expect(createItem).toHaveBeenCalledOnce());
    const form = createItem.mock.calls[0][0] as FormData;
    expect(form.get('image')).toBeInstanceOf(File);
    expect(form.get('purchase_date')).toBe('2026-06-10');
    expect(form.get('purchase_price')).toBe('12.50');
  });
});
