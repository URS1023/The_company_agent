export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }
  });
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("upload", file);
  const response = await fetch(path, { method: "POST", body: form, credentials: "include" });
  if (!response.ok) throw new Error(`上传失败（${response.status}）`);
  return response.json() as Promise<T>;
}

export async function apiUploadMany<T>(path: string, files: File[]): Promise<T> {
  const form = new FormData();
  for (const file of files) form.append("uploads", file);
  const response = await fetch(path, { method: "POST", body: form, credentials: "include" });
  if (!response.ok) {
    let detail = `上传失败（${response.status}）`;
    try { detail = (await response.json()).detail ?? detail; } catch { /* keep status */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
