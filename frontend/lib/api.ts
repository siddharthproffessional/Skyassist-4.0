// Same-origin API client. Mutations carry X-SkyAssist-Client (CSRF guard); the session is an HttpOnly cookie.
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (r.ok) {
    const ct = r.headers.get("content-type") || "";
    return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
  }
  let msg = r.statusText;
  let code: string | undefined;
  try {
    const j = await r.json();
    const d = j.detail;
    if (typeof d === "string") msg = d;
    else if (d && typeof d === "object") {
      msg = d.message || JSON.stringify(d);
      code = d.code;
    }
  } catch {}
  throw new ApiError(r.status, msg, code);
}

export async function get<T = any>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { credentials: "same-origin", cache: "no-store" }));
}

export async function post<T = any>(path: string, body: unknown = {}): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-SkyAssist-Client": "web" },
      body: JSON.stringify(body ?? {}),
    }),
  );
}
