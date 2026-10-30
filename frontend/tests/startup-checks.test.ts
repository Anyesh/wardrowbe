import { describe, expect, it } from "vitest";
import { nextauthSecretProblem } from "@/lib/startup-checks";

const DEFAULT = "change-me-in-production-use-openssl-rand-hex-32";

describe("nextauthSecretProblem", () => {
  it.each([
    ["oidc", { OIDC_ISSUER_URL: "https://auth.example.com" }],
    ["forward auth", { FORWARD_AUTH_SECRET: "p".repeat(32) }],
    [
      "both",
      {
        OIDC_ISSUER_URL: "https://auth.example.com",
        FORWARD_AUTH_SECRET: "p".repeat(32),
      },
    ],
  ])("refuses the default secret with %s configured", (_name, auth) => {
    expect(
      nextauthSecretProblem({ NEXTAUTH_SECRET: DEFAULT, ...auth }),
    ).toMatch(/NEXTAUTH_SECRET/);
    expect(
      nextauthSecretProblem({
        NEXTAUTH_SECRET: "change-me-in-production",
        ...auth,
      }),
    ).not.toBeNull();
  });

  it.each([
    ["dev mode without real auth", { NEXTAUTH_SECRET: DEFAULT }],
    [
      "empty auth settings",
      {
        NEXTAUTH_SECRET: DEFAULT,
        OIDC_ISSUER_URL: "",
        FORWARD_AUTH_SECRET: "",
      },
    ],
    [
      "a custom secret",
      {
        NEXTAUTH_SECRET: "a-strong-secret",
        OIDC_ISSUER_URL: "https://auth.example.com",
      },
    ],
    ["no secret set", { OIDC_ISSUER_URL: "https://auth.example.com" }],
  ])("allows %s", (_name, env) => {
    expect(nextauthSecretProblem(env)).toBeNull();
  });
});
