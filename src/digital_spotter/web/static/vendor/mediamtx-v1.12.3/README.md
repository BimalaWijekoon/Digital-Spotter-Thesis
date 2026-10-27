# Pinned MediaMTX WebRTC reader

Unmodified MIT-licensed upstream asset from release **v1.12.3**:

- `reader.js`: https://github.com/bluenviron/mediamtx/blob/v1.12.3/internal/servers/webrtc/reader.js
- `LICENSE`: https://github.com/bluenviron/mediamtx/blob/v1.12.3/LICENSE
- Reader SHA256: `1d899415b8065a5cb2602cdeb968dd07497d2a3f009e904809435202f8c44bce`
- License SHA256: `ecae73b0a23185a35a1222edc0aae5245bb9739420bad0125b0c42e935301a80`

This is a browser dependency pin, not a server upgrade. The research preview
tests this reader against the existing MediaMTX v1.9.1 server. Refer to the dated
M3-04 evidence for measured compatibility; matching WHEP APIs alone are not proof.
Do not replace this file with latest/main or edit it in place without updating
the pin and rerunning focused browser evidence.

This version has no bearer-token support. The research composition rejects
nonempty tokens; it is loopback-only and is not the authenticated product UI.
The constants in upstream codec capability probes are synthetic SDP examples,
not provisioned Digital Spotter credentials.
