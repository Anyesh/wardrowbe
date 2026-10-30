import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { PhotoPicker, type DraftPhoto } from '@/components/photo-picker';
import { nextFreeView } from '@/components/item-photos/photo-manager';
import { ItemGallery, type GalleryPhoto } from '@/components/item-photos/item-gallery';
import { categoryOfType } from '@/lib/types';

// next/image needs the Next runtime; a plain img is enough to check what is shown.
vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
  default: (props: { src: string; alt: string }) => <img src={props.src} alt={props.alt} />,
}));

const draft = (id: string, type: DraftPhoto['type']): DraftPhoto => ({
  id,
  file: new File(['image'], `${id}.png`, { type: 'image/png' }),
  preview: `blob:${id}`,
  type,
});

function Editor({ initial }: { initial: DraftPhoto[] }) {
  const [photos, setPhotos] = useState(initial);
  return (
    <>
      <PhotoPicker photos={photos} onChange={setPhotos} />
      <output data-testid="order">{photos.map((p) => `${p.id}:${p.type}`).join(',')}</output>
    </>
  );
}

describe('photo selection before upload', () => {
  it('changes cover, labels, order and removes without uploading', () => {
    vi.stubGlobal('URL', { ...URL, revokeObjectURL: vi.fn(), createObjectURL: vi.fn() });
    render(<Editor initial={[draft('front', 'front'), draft('back', 'back')]} />);
    const order = screen.getByTestId('order');

    fireEvent.click(screen.getAllByRole('button', { name: 'cover' })[1]);
    expect(order).toHaveTextContent('back:back,front:front');

    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'detail' } });
    expect(order).toHaveTextContent('back:detail,front:front');

    fireEvent.click(screen.getAllByRole('button', { name: 'next' })[0]);
    expect(order).toHaveTextContent('front:front,back:detail');

    fireEvent.click(screen.getAllByRole('button', { name: 'remove' })[1]);
    expect(order).toHaveTextContent(/^front:front$/);
    expect(within(screen.getAllByRole('combobox')[0]).getAllByRole('option')).toHaveLength(4);
    vi.unstubAllGlobals();
  });

  it('keeps a single front and a single back', () => {
    vi.stubGlobal('URL', { ...URL, revokeObjectURL: vi.fn(), createObjectURL: vi.fn() });
    render(<Editor initial={[draft('a', 'front'), draft('b', 'other')]} />);
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'front' } });
    expect(screen.getByTestId('order')).toHaveTextContent('a:other,b:front');
    vi.unstubAllGlobals();
  });

  it('fills the free side first for new photos', () => {
    expect(nextFreeView([])).toBe('front');
    expect(nextFreeView(['front'])).toBe('back');
    expect(nextFreeView(['back', 'front', 'detail'])).toBeNull();
  });
});

describe('item gallery', () => {
  const photos: GalleryPhoto[] = [
    { id: 'cover', src: '/cover.jpg', view: 'front' },
    { id: 'detail', src: '/detail.jpg', view: 'detail' },
    { id: 'back', src: '/back.jpg', view: 'back' },
  ];

  function Gallery() {
    const [index, setIndex] = useState(0);
    return <ItemGallery photos={photos} index={index} onIndexChange={setIndex} alt="Shirt" />;
  }

  it('switches between front and back and wraps around with the arrows', () => {
    render(<Gallery />);
    const main = () => screen.getAllByRole('img')[0];
    expect(main()).toHaveAttribute('src', '/cover.jpg');

    fireEvent.click(screen.getByRole('button', { name: 'back', pressed: false }));
    expect(main()).toHaveAttribute('src', '/back.jpg');

    fireEvent.click(screen.getByRole('button', { name: 'next' }));
    expect(main()).toHaveAttribute('src', '/cover.jpg');

    fireEvent.click(screen.getByRole('button', { name: 'previous' }));
    expect(main()).toHaveAttribute('src', '/back.jpg');
  });

  it('shows no front/back switch for a single photo', () => {
    render(<ItemGallery photos={[photos[0]]} index={0} onIndexChange={() => {}} alt="Shirt" />);
    expect(screen.queryByRole('button', { name: 'previous' })).toBeNull();
    expect(screen.queryByRole('group', { name: 'frontBack' })).toBeNull();
  });
});

describe('wardrobe sections', () => {
  it('puts jewelry under accessories and unknown types under clothing', () => {
    expect(categoryOfType('ring')).toBe('accessories');
    expect(categoryOfType('earrings')).toBe('accessories');
    expect(categoryOfType('boots')).toBe('footwear');
    expect(categoryOfType('jeans')).toBe('clothing');
    expect(categoryOfType('unknown')).toBe('clothing');
  });
});
