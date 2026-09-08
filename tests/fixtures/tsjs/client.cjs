// A request whose address is decided at run time.

async function call(endpoint) {
  return fetch(endpoint);
}

module.exports = { call };
