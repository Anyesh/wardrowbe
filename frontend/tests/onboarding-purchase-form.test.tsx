import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OnboardingPage from '@/app/onboarding/page';

const { createItem } = vi.hoisted(() => ({ createItem: vi.fn() }));
const createObjectURL = URL.createObjectURL;
const revokeObjectURL = URL.revokeObjectURL;

vi.mock('@/lib/hooks/use-items', () => ({
  useCreateItem: () => ({ mutateAsync: createItem, isPending: false }),
}));

vi.mock('@/lib/hooks/use-auth', () => ({
  useAuth: () => ({ user: { onboarding_completed: false }, isAuthenticated: true, isLoading: false, session: null }),
}));

vi.mock('@/lib/hooks/use-family', () => ({
  useCreateFamily: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useJoinFamily: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false }),
}));

vi.mock('@/lib/hooks/use-preferences', () => ({
  useUpdatePreferences: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingTypes: () => [{ value: 'shirt', label: 'Shirt' }],
  useClothingColors: () => [],
}));

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: {
    children: React.ReactNode;
    value: string;
    onValueChange: (value: string) => void;
  }) => <select aria-label="item type" value={value} onChange={(event) => onValueChange(event.target.value)}>{children}</select>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectValue: () => <option value="">Select type</option>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
}));

vi.mock('@/components/ui/slider', () => ({
  Slider: () => <input type="range" readOnly />,
}));

function renderUploadStep() {
  const { container } = render(
    <QueryClientProvider client={new QueryClient()}>
      <OnboardingPage />
    </QueryClientProvider>
  );
  fireEvent.click(screen.getByRole('button', { name: 'welcome.getStarted' }));
  for (let step = 0; step < 3; step++) {
    fireEvent.click(screen.getByRole('button', { name: 'skipForNow' }));
  }
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: { files: [new File(['photo'], 'shirt.jpg', { type: 'image/jpeg' })] },
  });
  fireEvent.change(screen.getByRole('combobox', { name: 'item type' }), { target: { value: 'shirt' } });
}

describe('onboarding first-item purchase fields', () => {
  beforeEach(() => {
    createItem.mockReset().mockResolvedValue({});
    URL.createObjectURL = vi.fn(() => 'blob:preview');
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
  });

  it('uploads normalized purchase details with the first item', async () => {
    renderUploadStep();
    fireEvent.change(screen.getByLabelText('date'), { target: { value: '2026-06-10' } });
    fireEvent.change(screen.getByLabelText('amount'), { target: { value: '12,50' } });
    fireEvent.click(screen.getByRole('button', { name: 'firstItem.addToWardrobe' }));

    await waitFor(() => expect(createItem).toHaveBeenCalledOnce());
    const form = createItem.mock.calls[0][0] as FormData;
    expect(form.get('image')).toBeInstanceOf(File);
    expect(form.get('type')).toBe('shirt');
    expect(form.get('purchase_date')).toBe('2026-06-10');
    expect(form.get('purchase_price')).toBe('12.50');
    await waitFor(() => expect(screen.getByText('complete.title')).toBeInTheDocument());
  });

  it('keeps optional purchase fields out of the request when blank', async () => {
    renderUploadStep();
    fireEvent.click(screen.getByRole('button', { name: 'firstItem.addToWardrobe' }));

    await waitFor(() => expect(createItem).toHaveBeenCalledOnce());
    const form = createItem.mock.calls[0][0] as FormData;
    expect(form.has('purchase_date')).toBe(false);
    expect(form.has('purchase_price')).toBe(false);
  });

  it('shows validation and prevents upload for an invalid amount', () => {
    renderUploadStep();
    fireEvent.change(screen.getByLabelText('amount'), { target: { value: '12.345' } });
    fireEvent.click(screen.getByRole('button', { name: 'firstItem.addToWardrobe' }));

    expect(screen.getByRole('alert')).toHaveTextContent('invalidAmount');
    expect(screen.getByLabelText('amount')).toHaveAttribute('aria-invalid', 'true');
    expect(createItem).not.toHaveBeenCalled();
  });
});
