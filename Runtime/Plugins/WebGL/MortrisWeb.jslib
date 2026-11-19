// Browser side of Mortris Analytics for WebGL players: localStorage, page visibility, and a keepalive POST that outlives the page.
var MortrisWeb = {
  MortrisStorageGet: function (keyPtr) {
    var value = "";
    try { value = window.localStorage.getItem(UTF8ToString(keyPtr)) || ""; } catch (e) { } // blocked storage (privacy settings, sandboxed iframe) reads as empty
    var size = lengthBytesUTF8(value) + 1;
    var buffer = _malloc(size);
    stringToUTF8(value, buffer, size);
    return buffer; // freed by the IL2CPP string marshaller
  },

  MortrisStorageSet: function (keyPtr, valuePtr) {
    try {
      var key = UTF8ToString(keyPtr), value = UTF8ToString(valuePtr);
      if (value.length === 0) window.localStorage.removeItem(key); else window.localStorage.setItem(key, value);
      return 1;
    } catch (e) {
      return 0; // QuotaExceededError, or storage blocked: the SDK trims its queue and keeps going in memory
    }
  },

  // A POST that the browser completes even when the tab is closed next. Bodies over 64 KiB, and anything beyond the page's shared 64 KiB in-flight
  // budget, are refused by the browser: the caller keeps the events queued either way.
  MortrisKeepalive: function (urlPtr, bearerPtr, bodyPtr, bodyLength, gzip) {
    try {
      var headers = { "Content-Type": "application/json" };
      if (gzip) headers["Content-Encoding"] = "gzip";
      var bearer = UTF8ToString(bearerPtr);
      if (bearer) headers["Authorization"] = "Bearer " + bearer;
      var body = HEAPU8.slice(bodyPtr, bodyPtr + bodyLength); // a copy: the managed array may move or be collected after this call returns
      fetch(UTF8ToString(urlPtr), { method: "POST", keepalive: true, mode: "cors", credentials: "omit", headers: headers, body: body })
        .catch(function () { });
      return 1;
    } catch (e) {
      return 0;
    }
  },

  // visibilitychange is the last event a mobile browser reliably fires before it may discard the page; pagehide covers desktop close and
  // navigation (and bfcache), pageshow a page restored from bfcache. Repeated notifications of the same state are dropped.
  MortrisWatchVisibility: function (callback) {
    var last = -1;
    var notify = function (hidden) {
      if (hidden === last) return;
      last = hidden;
      {{{ makeDynCall('vi', 'callback') }}}(hidden);
    };
    document.addEventListener("visibilitychange", function () { notify(document.visibilityState === "hidden" ? 1 : 0); });
    window.addEventListener("pagehide", function () { notify(1); });
    window.addEventListener("pageshow", function (event) { if (event.persisted) notify(0); });
  },
};

mergeInto(LibraryManager.library, MortrisWeb);
