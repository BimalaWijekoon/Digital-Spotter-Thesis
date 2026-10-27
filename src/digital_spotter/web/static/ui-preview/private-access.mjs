const TAILSCALE_DNS_SUFFIX = '.ts.net';

function isDnsLabel(value) {
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(value);
}

function isTailscaleDnsName(hostname) {
  const normalized = String(hostname ?? '').toLowerCase();
  if (!normalized.endsWith(TAILSCALE_DNS_SUFFIX)) return false;
  const labels = normalized.split('.');
  return labels.length >= 4 && labels.every(isDnsLabel);
}

export function isPrivateResearchOrigin(locationLike) {
  if (!locationLike) return false;
  if (locationLike.protocol === 'http:' && locationLike.hostname === '127.0.0.1') {
    return true;
  }
  return locationLike.protocol === 'https:' && isTailscaleDnsName(locationLike.hostname);
}

export function resolvePrivateWhepUrl(config, locationLike) {
  if (!isPrivateResearchOrigin(locationLike)) {
    throw new TypeError('camera requires a private research origin');
  }
  if (locationLike.protocol === 'http:') {
    if (typeof config?.loopback_whep_url !== 'string') {
      throw new TypeError('loopback WHEP configuration is missing');
    }
    return new URL(config.loopback_whep_url).toString();
  }
  const port = Number(config?.tailscale_https_port);
  const path = config?.whep_path;
  if (!Number.isInteger(port) || port < 1 || port > 65535
      || typeof path !== 'string' || !path.startsWith('/') || !path.endsWith('/whep')) {
    throw new TypeError('Tailscale WHEP configuration is invalid');
  }
  return new URL(`https://${locationLike.hostname}:${port}${path}`).toString();
}
