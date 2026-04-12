"use client";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { LightboxImage } from "./lightbox-adapters";

type LightboxState = {
  visible: boolean;
  images: LightboxImage[];
  index: number;
  currentItemId?: string;
};

type LightboxContextValue = LightboxState & {
  open: (images: LightboxImage[], initialIndex: number, currentItemId?: string) => void;
  close: () => void;
  setIndex: (index: number) => void;
};

const LightboxContext = createContext<LightboxContextValue | null>(null);

export function LightboxProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LightboxState>({
    visible: false,
    images: [],
    index: 0,
    currentItemId: undefined,
  });

  const open = useCallback(
    (images: LightboxImage[], initialIndex: number, currentItemId?: string) => {
      setState({ visible: true, images, index: initialIndex, currentItemId });
    },
    [],
  );

  const close = useCallback(() => {
    setState({ visible: false, images: [], index: 0, currentItemId: undefined });
  }, []);

  const setIndex = useCallback((index: number) => {
    setState((prev) => ({ ...prev, index }));
  }, []);

  const value = useMemo(
    () => ({ ...state, open, close, setIndex }),
    [state, open, close, setIndex],
  );

  return <LightboxContext.Provider value={value}>{children}</LightboxContext.Provider>;
}

export function useLightbox(): LightboxContextValue {
  const ctx = useContext(LightboxContext);
  if (!ctx) throw new Error("useLightbox must be used within LightboxProvider");
  return ctx;
}
