import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { useNtfyDefaults } from "@/lib/hooks/use-notifications";

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { accessToken: "jwt" }, status: "authenticated" }),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: { get: vi.fn() },
  setAccessToken: vi.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe("useNtfyDefaults", () => {
  it("reads the defaults through the authenticated api client", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      server: "https://ntfy.sh",
      has_token: true,
    });

    const { result } = renderHook(() => useNtfyDefaults(), { wrapper });

    await waitFor(() =>
      expect(result.current.data).toEqual({
        server: "https://ntfy.sh",
        has_token: true,
      }),
    );
    expect(api.get).toHaveBeenCalledWith("/notifications/defaults/ntfy");
  });

  it("does not fetch while disabled", () => {
    vi.mocked(api.get).mockClear();

    renderHook(() => useNtfyDefaults(false), { wrapper });

    expect(api.get).not.toHaveBeenCalled();
  });
});
