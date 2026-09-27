// Thin browser client for the HTTP API.
export class Client extends BaseClient {
  constructor(baseUrl) {
    super();
    this.baseUrl = baseUrl;
  }

  async fetchUser(id) {
    const res = await fetch(`${this.baseUrl}/users/${id}`);
    return res.json();
  }
}

export function buildHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}

export const retry = async (fn, times) => {
  for (let i = 0; i < times; i++) {
    try { return await fn(); } catch (e) { if (i === times - 1) throw e; }
  }
};
