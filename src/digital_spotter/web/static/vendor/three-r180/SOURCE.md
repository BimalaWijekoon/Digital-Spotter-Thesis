# Three.js r180 / 0.180.0

MIT licensed; original LICENSE retained. Downloaded 2026-10-22 from the pinned
official `mrdoob/three.js` r180 release, not a moving branch. No npm installation,
CDN request, external font, texture or model download is needed at runtime.

Release: https://github.com/mrdoob/three.js/releases/tag/r180

| File | Source under https://raw.githubusercontent.com/mrdoob/three.js/r180/ | Bytes | SHA256 |
| --- | --- | ---: | --- |
| three.module.min.js | build/three.module.min.js | 338908 | e2b5ee6bccd38fd6d8a2428546b83c5f2426d84b152ef82be8055556e3b40eb6 |
| three.core.min.js | build/three.core.min.js | 381124 | 61ba0df005b05991361d040d8ff670e1aadfd0ce7aeebd1fdb0725957a8957de |
| LICENSE | LICENSE | 1081 | bfe119ea4fd413f5f7ca3fcd63adb0c4a073ed39daa2fe7d3e6b769e21272601 |

Used only by the lazily loaded browser-side demo mannequin. WebGL 2 required.
This pinned renderer is not a pose estimator, model runtime or BLE adapter.

2026-10-23: added unchanged glTF loader and its one utility dependency from the
same official r180 release (same MIT license). The local import map resolves
`three` to the already vendored module, with no npm or CDN dependency.

| Local file | Source under the same pinned raw URL | Bytes | SHA256 |
|---|---|---:|---|
| loaders/GLTFLoader.js | examples/jsm/loaders/GLTFLoader.js | 114739 | 67ac5551fdafa6e349bd80c8f8e5e39c136d6b2fb1ad647db9abb21dc86f9e4a |
| utils/BufferGeometryUtils.js | examples/jsm/utils/BufferGeometryUtils.js | 35539 | fda7e946b8e0b5ab39b779206589e7a1079a22eb24efb89d7223e03fdfb1f751 |
