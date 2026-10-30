import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { ProfileLocaleSync } from "@/components/profile-locale-sync";

const session = vi.hoisted(() => ({ status: "authenticated", locale: "fr", token: "jwt" as string | null }));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data:
      session.status === "authenticated"
        ? { accessToken: session.token ?? undefined, syncError: session.token ? undefined : "down" }
        : null,
    status: session.status,
  }),
}));

vi.mock("next-intl", () => ({
  useLocale: () => session.locale,
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: { get: vi.fn(), patch: vi.fn() },
  setAccessToken: vi.fn(),
}));

function renderSync() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <ProfileLocaleSync />
    </QueryClientProvider>,
  );
  return { client, view };
}

describe("ProfileLocaleSync", () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset();
    vi.mocked(api.patch).mockReset();
    session.status = "authenticated";
    session.locale = "fr";
    session.token = "jwt";
    document.cookie = "NEXT_LOCALE=; path=/; max-age=0";
  });

  it("saves the language the UI renders in when the profile differs", async () => {
    vi.mocked(api.get).mockResolvedValue({ locale: "en" });
    vi.mocked(api.patch).mockResolvedValue({ locale: "fr" });

    renderSync();

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/users/me", { locale: "fr" }));
    expect(api.patch).toHaveBeenCalledTimes(1);
  });

  it("saves the language just picked in the switcher", async () => {
    document.cookie = "theme=dark; path=/";
    document.cookie = "NEXT_LOCALE=de; path=/";
    session.locale = "de";
    vi.mocked(api.get).mockResolvedValue({ locale: "en" });
    vi.mocked(api.patch).mockResolvedValue({ locale: "de" });

    renderSync();

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/users/me", { locale: "de" }));
  });

  it("leaves a profile that already matches alone", async () => {
    vi.mocked(api.get).mockResolvedValue({ locale: "fr" });

    renderSync();

    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me"));
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("does not ask for a profile before sign-in", async () => {
    session.status = "unauthenticated";

    renderSync();

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.get).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("does not ask for a profile when the backend sync failed", async () => {
    session.token = null;

    renderSync();

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.get).not.toHaveBeenCalled();
  });

  it("does not write back the language of a tab another tab has since switched away from", async () => {
    document.cookie = "NEXT_LOCALE=de; path=/";
    session.locale = "en";
    vi.mocked(api.get).mockResolvedValue({ locale: "de" });

    renderSync();

    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/users/me"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("does not retry a failed save on every profile refetch", async () => {
    vi.mocked(api.get).mockResolvedValue({ locale: "en" });
    vi.mocked(api.patch).mockRejectedValue(new Error("offline"));

    const { client } = renderSync();
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));

    await client.refetchQueries();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.patch).toHaveBeenCalledTimes(1);
  });

  it("saves again when the user switches language", async () => {
    vi.mocked(api.get).mockResolvedValue({ locale: "en" });
    vi.mocked(api.patch).mockResolvedValue({});

    const { client, view } = renderSync();
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/users/me", { locale: "fr" }));

    session.locale = "de";
    view.rerender(
      <QueryClientProvider client={client}>
        <ProfileLocaleSync />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/users/me", { locale: "de" }));
  });
});
