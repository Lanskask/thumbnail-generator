/**
 * Cloudflare Worker with the same HTTP shape as the GCP `get_upload_url` function,
 * so frontend/index.html works unchanged (it only needs its endpoint set to "/api").
 *
 *   POST /api?action=upload            {"filename","contentType"} -> {"uploadUrl","objectName"}
 *   PUT  /api/put/<objectName>         raw image bytes; resizes to <=200x200 and stores in R2
 *   GET  /api?action=download&objectName=<name> -> {"exists", "downloadUrl"}
 *   GET  /api/thumb/<thumbObjectName>  the thumbnail
 *
 *   GET  / (or /index.html)            the upload page, bundled into the Worker (see scripts/gen-frontend.mjs)
 *
 * Difference from GCP: the browser PUTs to the Worker (not to a signed bucket URL) and the
 * thumbnail is made in the same request, so there is one bucket and no event trigger.
 */

import FRONTEND_HTML from "./frontend.generated";

export interface Env {
  THUMBS: R2Bucket;
  IMAGES: ImagesBinding;
}

export const THUMBNAIL_SIZE = 200;
export const THUMBNAIL_PREFIX = "thumb_";
// Images binding accepts up to 20 MB input (official docs, checked 2026-10-03).
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const ALLOWED_CONTENT_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);
// gif output is not confirmed for the Images binding, so gif input is written as png.
const OUTPUT_FORMAT: Record<string, "image/png" | "image/jpeg" | "image/webp"> = {
  "image/png": "image/png",
  "image/jpeg": "image/jpeg",
  "image/webp": "image/webp",
  "image/gif": "image/png",
};
const OBJECT_NAME_RE = /^\d+-[0-9a-f]{8}-[A-Za-z0-9._-]+$/;

export function sanitizeFilename(filename: string): string {
  const base = filename.split(/[\\/]/).pop() ?? "";
  return base.replace(/[^A-Za-z0-9._-]/g, "_") || "upload";
}

export function isValidObjectName(name: string): boolean {
  return OBJECT_NAME_RE.test(name) && name.length <= 200;
}

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function handleUpload(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => ({}))) as { filename?: string; contentType?: string };
  if (!body.filename) return json({ error: "filename is required" }, 400);
  if (!body.contentType || !ALLOWED_CONTENT_TYPES.has(body.contentType)) {
    return json({ error: `contentType must be one of ${[...ALLOWED_CONTENT_TYPES].sort().join(", ")}` }, 400);
  }
  const rand = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  const objectName = `${Math.floor(Date.now() / 1000)}-${rand}-${sanitizeFilename(body.filename)}`;
  return json({ uploadUrl: `/api/put/${objectName}`, objectName });
}

async function handlePut(request: Request, env: Env, objectName: string): Promise<Response> {
  if (!isValidObjectName(objectName)) return json({ error: "bad object name" }, 400);
  const contentType = request.headers.get("content-type") ?? "";
  if (!ALLOWED_CONTENT_TYPES.has(contentType)) return json({ error: "unsupported content type" }, 415);
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > MAX_UPLOAD_BYTES) return json({ error: "file too large" }, 413);
  if (!request.body) return json({ error: "empty body" }, 400);

  const result = await env.IMAGES.input(request.body)
    .transform({ width: THUMBNAIL_SIZE, height: THUMBNAIL_SIZE, fit: "scale-down" })
    .output({ format: OUTPUT_FORMAT[contentType] });
  const thumb = result.response();
  await env.THUMBS.put(`${THUMBNAIL_PREFIX}${objectName}`, thumb.body, {
    httpMetadata: { contentType: thumb.headers.get("content-type") ?? OUTPUT_FORMAT[contentType] },
  });
  return new Response(null, { status: 200 });
}

async function handleDownload(url: URL, env: Env): Promise<Response> {
  const objectName = url.searchParams.get("objectName") ?? "";
  if (!objectName) return json({ error: "objectName is required" }, 400);
  const thumbName = `${THUMBNAIL_PREFIX}${objectName}`;
  if (!isValidObjectName(objectName) || !(await env.THUMBS.head(thumbName))) return json({ exists: false });
  return json({ exists: true, downloadUrl: `/api/thumb/${thumbName}` });
}

async function handleThumb(env: Env, thumbName: string): Promise<Response> {
  if (!thumbName.startsWith(THUMBNAIL_PREFIX) || !isValidObjectName(thumbName.slice(THUMBNAIL_PREFIX.length))) {
    return json({ error: "not found" }, 404);
  }
  const obj = await env.THUMBS.get(thumbName);
  if (!obj) return json({ error: "not found" }, 404);
  return new Response(obj.body, {
    headers: {
      "content-type": obj.httpMetadata?.contentType ?? "application/octet-stream",
      "cache-control": "private, max-age=600",
    },
  });
}

export async function handle(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "");
  const action = url.searchParams.get("action");

  if ((path === "" || path === "/index.html") && request.method === "GET") {
    return new Response(FRONTEND_HTML, { headers: { "content-type": "text/html; charset=utf-8" } });
  }
  if (path === "/api" && action === "upload" && request.method === "POST") return handleUpload(request);
  if (path === "/api" && action === "download" && request.method === "GET") return handleDownload(url, env);
  if (path.startsWith("/api/put/") && request.method === "PUT") {
    return handlePut(request, env, path.slice("/api/put/".length));
  }
  if (path.startsWith("/api/thumb/") && request.method === "GET") {
    return handleThumb(env, path.slice("/api/thumb/".length));
  }
  return json({ error: "unknown action or wrong method" }, 400);
}

export default { fetch: handle } satisfies ExportedHandler<Env>;
