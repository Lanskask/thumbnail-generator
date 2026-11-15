import { describe, expect, it } from "vitest";
import { handle, isValidObjectName, sanitizeFilename, type Env } from "../src/index";

function fakeEnv(opts: { exists?: boolean } = {}) {
  const stored: Record<string, { body: unknown; contentType?: string }> = {};
  const transforms: unknown[] = [];
  const env = {
    THUMBS: {
      put: async (key: string, body: unknown, o?: { httpMetadata?: { contentType?: string } }) => {
        // Real R2 rejects streams of unknown length (found in the local wrangler dev run).
        if (body instanceof ReadableStream) throw new TypeError("stream must have a known length");
        stored[key] = { body, contentType: o?.httpMetadata?.contentType };
      },
      head: async (key: string) => (opts.exists || stored[key] ? {} : null),
      get: async (key: string) =>
        stored[key] ? { body: "bytes", httpMetadata: { contentType: stored[key].contentType } } : null,
    },
    IMAGES: {
      input: () => ({
        transform: (t: unknown) => {
          transforms.push(t);
          return {
            output: async (o: { format: string }) => ({
              response: () => new Response("thumb-bytes", { headers: { "content-type": o.format } }),
            }),
          };
        },
      }),
    },
  } as unknown as Env;
  return { env, stored, transforms };
}

const req = (url: string, init?: RequestInit) => new Request(`https://x.test${url}`, init);

describe("sanitizeFilename / isValidObjectName", () => {
  it("replaces unsafe characters and strips paths", () => {
    expect(sanitizeFilename("../a b/cat (1).jpg")).toBe("cat__1_.jpg");
    expect(sanitizeFilename("")).toBe("upload");
  });
  it("accepts minted names only", () => {
    expect(isValidObjectName("1699999999-abcdef12-cat.jpg")).toBe(true);
    expect(isValidObjectName("../secret")).toBe(false);
  });
});

describe("upload action", () => {
  it("returns an upload URL and object name", async () => {
    const { env } = fakeEnv();
    const res = await handle(
      req("/api?action=upload", { method: "POST", body: JSON.stringify({ filename: "cat.jpg", contentType: "image/jpeg" }) }),
      env,
    );
    const data = (await res.json()) as { uploadUrl: string; objectName: string };
    expect(res.status).toBe(200);
    expect(isValidObjectName(data.objectName)).toBe(true);
    expect(data.uploadUrl).toBe(`/api/put/${data.objectName}`);
  });
  it("rejects missing filename and bad content type", async () => {
    const { env } = fakeEnv();
    const a = await handle(req("/api?action=upload", { method: "POST", body: JSON.stringify({ contentType: "image/png" }) }), env);
    const b = await handle(req("/api?action=upload", { method: "POST", body: JSON.stringify({ filename: "a.txt", contentType: "text/plain" }) }), env);
    expect([a.status, b.status]).toEqual([400, 400]);
  });
});

describe("put -> download -> thumb", () => {
  const name = "1699999999-abcdef12-cat.jpg";
  it("resizes to 200x200 scale-down, stores thumb_ key, then serves it", async () => {
    const { env, stored, transforms } = fakeEnv();
    const put = await handle(req(`/api/put/${name}`, { method: "PUT", headers: { "content-type": "image/jpeg" }, body: "img" }), env);
    expect(put.status).toBe(200);
    expect(transforms).toEqual([{ width: 200, height: 200, fit: "scale-down" }]);
    expect(Object.keys(stored)).toEqual([`thumb_${name}`]);

    const dl = (await (await handle(req(`/api?action=download&objectName=${name}`), env)).json()) as { exists: boolean; downloadUrl: string };
    expect(dl).toEqual({ exists: true, downloadUrl: `/api/thumb/thumb_${name}` });
    const thumb = await handle(req(dl.downloadUrl), env);
    expect(thumb.status).toBe(200);
  });
  it("reports exists:false before the thumbnail exists", async () => {
    const { env } = fakeEnv();
    const dl = await (await handle(req(`/api?action=download&objectName=${name}`), env)).json();
    expect(dl).toEqual({ exists: false });
  });
  it("rejects bad names, wrong type and oversize uploads", async () => {
    const { env } = fakeEnv();
    const bad = await handle(req("/api/put/evil.jpg", { method: "PUT", headers: { "content-type": "image/jpeg" }, body: "x" }), env);
    const type = await handle(req(`/api/put/${name}`, { method: "PUT", headers: { "content-type": "text/plain" }, body: "x" }), env);
    const big = await handle(req(`/api/put/${name}`, { method: "PUT", headers: { "content-type": "image/png", "content-length": String(11 * 1024 * 1024) }, body: "x" }), env);
    expect([bad.status, type.status, big.status]).toEqual([400, 415, 413]);
  });
  it("does not serve non-thumb keys", async () => {
    const { env } = fakeEnv();
    expect((await handle(req("/api/thumb/secret"), env)).status).toBe(404);
  });
});

describe("frontend", () => {
  it("serves the bundled page at / with the API endpoint set to /api", async () => {
    const { env } = fakeEnv();
    const res = await handle(req("/"), env);
    expect(res.headers.get("content-type")).toContain("text/html");
    expect(await res.text()).toContain('const UPLOAD_FUNCTION_URL = "/api"');
  });
});
