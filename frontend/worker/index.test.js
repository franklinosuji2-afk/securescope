import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "./index.js";

const env = { BACKEND_URL: "https://api.example.org", PROXY_SECRET: "s3cret" };

afterEach(() => vi.unstubAllGlobals());

function stubBackend() {
  const calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request) => {
      calls.push(request);
      return new Response("{}", { status: 200 });
    }),
  );
  return calls;
}

describe("api proxy worker", () => {
  it("forwards the path, query and body to the backend", async () => {
    const calls = stubBackend();
    const request = new Request(
      "https://app.example.org/api/v1/scans?limit=5",
      {
        method: "POST",
        body: JSON.stringify({ url: "https://example.org" }),
        headers: {
          "content-type": "application/json",
          cookie: "ss_session=abc",
          "cf-connecting-ip": "203.0.113.9",
        },
      },
    );
    await worker.fetch(request, env);
    expect(calls[0].url).toBe("https://api.example.org/api/v1/scans?limit=5");
    expect(calls[0].method).toBe("POST");
    expect(calls[0].headers.get("cookie")).toBe("ss_session=abc");
    expect(await calls[0].text()).toContain("example.org");
  });

  it("adds the secret and the visitor address, replacing anything the visitor sent", async () => {
    const calls = stubBackend();
    const request = new Request("https://app.example.org/api/v1/ready", {
      headers: {
        "x-proxy-secret": "forged",
        "x-real-client-ip": "198.51.100.1",
        "x-forwarded-for": "198.51.100.2",
        "cf-connecting-ip": "203.0.113.9",
      },
    });
    await worker.fetch(request, env);
    const sent = calls[0].headers;
    expect(sent.get("x-proxy-secret")).toBe("s3cret");
    expect(sent.get("x-real-client-ip")).toBe("203.0.113.9");
    expect(sent.get("x-forwarded-for")).toBeNull();
  });

  it("never forwards a visitor-chosen address when Cloudflare supplied none", async () => {
    const calls = stubBackend();
    await worker.fetch(
      new Request("https://app.example.org/api/v1/ready", {
        headers: { "x-real-client-ip": "198.51.100.1" },
      }),
      env,
    );
    expect(calls[0].headers.get("x-real-client-ip")).toBeNull();
  });

  it("answers 503 instead of forwarding when it is not configured", async () => {
    const calls = stubBackend();
    const response = await worker.fetch(
      new Request("https://app.example.org/api/v1/ready"),
      {},
    );
    expect(response.status).toBe(503);
    expect(calls).toHaveLength(0);
  });
});
