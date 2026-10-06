var CACHE = "adlc-hub-v1";
var ASSETS = ["/ui/", "/ui/app.css", "/ui/app.js"];
self.addEventListener("install", function(e) {
  e.waitUntil(caches.open(CACHE).then(function(c) { return c.addAll(ASSETS); }));
});
self.addEventListener("fetch", function(e) {
  if (e.request.url.indexOf("/api/") !== -1) return;
  e.respondWith(caches.match(e.request).then(function(r) { return r || fetch(e.request); }));
});
