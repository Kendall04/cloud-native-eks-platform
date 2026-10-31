// Only attached to /api and /api/* behaviors selecting the existing HTTP API.
// Gateway's route allowlist/authentication remains authoritative; no identity made here.
function reject(code, message, method) {
  var r = {statusCode: code, headers: {
    "cache-control": {value: "no-store"},
    "content-type": {value: "application/json; charset=utf-8"},
    "x-content-type-options": {value: "nosniff"}
  }};
  if (method !== "HEAD") r.body = JSON.stringify({error: message});
  return r;
}
function handler(event) {
  var r = event.request, uri = r.uri;
  if (!/^\/api\//.test(uri) || /[%\\]/.test(uri) || /\/\//.test(uri) || /(^|\/)\.{1,2}(\/|$)/.test(uri)) return reject(400, "Invalid API path", r.method);
  if (["GET", "POST", "OPTIONS"].indexOf(r.method) === -1) return reject(405, "Unsupported API method", r.method);
  r.uri = uri.slice(4); // Strip exactly one /api; preserve querystring and bearer.
  r.cookies = {};
  Object.keys(r.headers).forEach(function (name) {
    if (name.toLowerCase() === "cookie" || name.toLowerCase().indexOf("x-platform-") === 0) delete r.headers[name];
  });
  return r;
}
