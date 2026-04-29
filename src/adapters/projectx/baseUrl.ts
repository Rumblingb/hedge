export const DEFAULT_PROJECTX_API_BASE_URL = "https://api.thefuturesdesk.projectx.com";

export function resolveProjectXApiBaseUrl(baseUrl?: string): string | undefined {
  if (!baseUrl) {
    return baseUrl;
  }

  const normalized = baseUrl.trim().replace(/\/$/, "");
  if (!normalized) {
    return undefined;
  }

  try {
    const url = new URL(normalized);
    const hostname = url.hostname.toLowerCase();
    const pathname = url.pathname.replace(/\/$/, "");

    if (
      hostname === "topstepx.com"
      || hostname === "www.topstepx.com"
      || hostname === "dashboard.projectx.com"
      || hostname === "gateway.docs.projectx.com"
      || (hostname === "topstep.com" && pathname.startsWith("/trade"))
    ) {
      return DEFAULT_PROJECTX_API_BASE_URL;
    }
  } catch {
    return normalized;
  }

  return normalized;
}
