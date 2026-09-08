// Minimal browser shim for the Node process object, replacing the
// /node/process.mjs polyfill that the vendored bitcoin-connect bundle
// imports. The bundle only checks that the import is truthy and never
// touches its members, but env/nextTick are included for safety.
const process = {
  arch: '',
  argv: [],
  env: {},
  platform: 'browser',
  nextTick: function (fn) {
    var args = Array.prototype.slice.call(arguments, 1);
    queueMicrotask(function () { fn.apply(null, args); });
  },
};

export default process;
