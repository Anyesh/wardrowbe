import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AddChannelDialog } from "@/components/notifications/add-channel-dialog";

const defaults = vi.hoisted(() => ({
  data: undefined as { server: string; has_token: boolean } | undefined,
}));

vi.mock("@/lib/hooks/use-notifications", () => ({
  useNtfyDefaults: () => ({ data: defaults.data }),
}));

function openDialog() {
  render(<AddChannelDialog onAdd={vi.fn()} isLoading={false} />);
  fireEvent.click(screen.getByText("channels.addChannel"));
}

describe("AddChannelDialog ntfy defaults", () => {
  beforeEach(() => {
    defaults.data = undefined;
  });

  it("prefills only the server, never a token", () => {
    defaults.data = { server: "https://ntfy.example.com", has_token: true };
    openDialog();

    expect((document.getElementById("server") as HTMLInputElement).value).toBe(
      "https://ntfy.example.com",
    );
    expect((document.getElementById("token") as HTMLInputElement).value).toBe(
      "",
    );
  });

  it("says the server token is used when the operator configured one", () => {
    defaults.data = { server: "https://ntfy.example.com/", has_token: true };
    openDialog();
    fireEvent.change(document.getElementById("server")!, {
      target: { value: "https://ntfy.example.com" },
    });

    expect(
      screen.getByText("channels.helpers.accessTokenServerDefault"),
    ).toBeTruthy();
  });

  it.each([
    [
      "no operator token",
      { server: "https://ntfy.example.com", has_token: false },
      undefined,
    ],
    [
      "another server",
      { server: "https://ntfy.example.com", has_token: true },
      "https://other.example.com",
    ],
  ])("keeps the generic token hint for %s", (_name, data, server) => {
    defaults.data = data;
    openDialog();
    if (server) {
      fireEvent.change(document.getElementById("server")!, {
        target: { value: server },
      });
    }

    expect(
      screen.getByText("channels.helpers.accessTokenOptional"),
    ).toBeTruthy();
    expect(
      screen.queryByText("channels.helpers.accessTokenServerDefault"),
    ).toBeNull();
  });

  it("keeps the generic hint once a token is typed", () => {
    defaults.data = { server: "https://ntfy.example.com", has_token: true };
    openDialog();
    fireEvent.change(document.getElementById("token")!, {
      target: { value: "tk_mine" },
    });

    expect(
      screen.queryByText("channels.helpers.accessTokenServerDefault"),
    ).toBeNull();
  });
});
