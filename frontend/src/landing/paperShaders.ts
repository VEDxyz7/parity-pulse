// Arc-length preserving bend adapted from the user-supplied ThreeUI Original source.
// Lighting stays local to this decorative surface; no financial data is synthesized.
export const paperVertex = /* glsl */ `
uniform float uTime;
uniform float uProgress;
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vPosition;

vec3 bend(vec2 uv) {
  float u = uv.x;
  float v = uv.y;
  float amplitude = 0.72 * (0.10 + pow(u, 1.35)) * (0.50 + 0.64 * v);
  float x = 0.0;
  float z = 0.0;
  float cx = 0.0;
  float cz = 0.0;
  for (int i = 0; i < 20; i++) {
    float s = (float(i) + 0.5) / 20.0;
    float theta = amplitude * sin(4.7 * s * u + 1.3 * v + uTime * 0.22);
    x += cos(theta) * u / 20.0;
    z += sin(theta) * u / 20.0;
    float ct = amplitude * sin(4.7 * s * 0.5 + 1.3 * v + uTime * 0.22);
    cx += cos(ct) * 0.5 / 20.0;
    cz += sin(ct) * 0.5 / 20.0;
  }
  float y = (v - 0.5) * 3.1;
  y += 0.025 * sin(u * 2.05 + uTime * 0.31) * sin(v * 3.14);
  return vec3((x - cx) * 2.3, y, (z - cz) * 2.3);
}
void main() {
  vUv = uv;
  vec3 p = bend(uv);
  vec3 du = bend(uv + vec2(0.002, 0.0)) - p;
  vec3 dv = bend(uv + vec2(0.0, 0.002)) - p;
  vNormal = normalize(mat3(modelMatrix) * normalize(cross(du, dv)));
  vec4 world = modelMatrix * vec4(p, 1.0);
  vPosition = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}`

export const paperFragment = /* glsl */ `
uniform sampler2D uPrint;
uniform vec3 uLight;
uniform float uTime;
uniform float uProgress;
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vPosition;
float grain(vec2 p) { return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
void main() {
  vec3 n = normalize(vNormal) * (gl_FrontFacing ? 1.0 : -1.0);
  vec3 eye = normalize(cameraPosition - vPosition);
  vec3 light = normalize(uLight - vPosition);
  float fresnel = pow(1.0 - abs(dot(n, eye)), 2.4);
  float spec = pow(max(dot(n, normalize(light + eye)), 0.0), 180.0);
  spec *= exp(-pow((vUv.y - 0.76) / 0.065, 2.0));
  vec3 rimLight = normalize(vec3(-1.4, -1.8, 4.0) - vPosition);
  float glint = pow(max(dot(n, normalize(rimLight + eye)), 0.0), 150.0);
  glint *= exp(-pow((vUv.y - 0.18) / 0.07, 2.0));
  float pin = exp(-pow((vUv.x - 0.25 - uLight.x * 0.015) / 0.025, 2.0));
  float soft = pow(max(dot(n, normalize(vec3(-2.0, 4.0, 5.0) + eye)), 0.0), 12.0);
  float reflection = pow(0.5 + 0.5 * sin(vUv.x * 8.0 + n.x * 5.0 + uTime * 0.08), 8.0);
  vec4 ink = texture2D(uPrint, vUv);
  float edge = min(min(vUv.x, 1.0-vUv.x), min(vUv.y, 1.0-vUv.y));
  float rim = 1.0 - smoothstep(0.0, 0.006, edge);
  vec3 emerald = mix(vec3(0.009,0.025,0.018), vec3(0.045,0.11,0.075), soft);
  emerald += reflection * vec3(0.008,0.018,0.012);
  emerald += spec * vec3(0.65,0.94,0.82) * (0.85 + uProgress * 0.4);
  emerald += glint * (vec3(0.02,0.04,0.035) + pin * vec3(0.70,0.95,0.98));
  emerald += fresnel * vec3(0.05,0.17,0.14) + rim * vec3(0.18,0.37,0.29);
  emerald += (grain(gl_FragCoord.xy) - 0.5) * 0.014;
  vec3 color = mix(emerald, ink.rgb, ink.a);
  float alpha = max(ink.a, 0.69 + fresnel * 0.15 + spec * 0.10);
  gl_FragColor = vec4(color, alpha);
  #include <colorspace_fragment>
}`
