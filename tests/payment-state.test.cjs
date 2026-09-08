/* Run: node --test tests/payment-state.test.cjs
 * Optional LNBITS_PAYMENT_TEST_SOURCE_REF=HEAD verifies a previous git revision.
 * No server, wallet, invoice, network access, or additional dependencies.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const {execFileSync} = require('node:child_process')
const test = require('node:test')
const vm = require('node:vm')

const source = process.env.LNBITS_PAYMENT_TEST_SOURCE_REF
  ? execFileSync(
      'git',
      [
        'show',
        `${process.env.LNBITS_PAYMENT_TEST_SOURCE_REF}:static/js/public.js`
      ],
      {encoding: 'utf8'}
    )
  : fs.readFileSync(path.join(__dirname, '../static/js/public.js'), 'utf8')
const hash = 'a'.repeat(64)

function setup() {
  let callbacks
  const sockets = []
  const calls = {
    closed: 0,
    launched: 0,
    refreshed: 0,
    notifications: [],
    timers: []
  }
  const bitcoinConnect = {
    init() {},
    launchPaymentModal(options) {
      callbacks = options
      calls.launched++
      return {
        setPaid() {
          throw new Error('Never require a preimage')
        }
      }
    },
    closeModal() {
      calls.closed++
      callbacks?.onCancelled()
    }
  }
  const context = {
    console,
    URL,
    window: {
      __bitcoinConnect: bitcoinConnect,
      location: {origin: 'http://localhost:5000'},
      clearTimeout() {},
      clearInterval() {},
      setTimeout(callback) {
        calls.timers.push(callback)
        return calls.timers.length
      }
    },
    WebSocket: class {
      constructor(url) {
        this.url = url
        this.closed = false
        sockets.push(this)
      }
      close() {
        this.closed = true
        this.onclose?.()
      }
    },
    Quasar: {
      Notify: {
        create(notification) {
          calls.notifications.push(notification)
        }
      }
    },
    LNbits: {
      api: {
        request: async () => ({
          data: {payment_hash: hash, payment_request: 'test-only-invoice'}
        })
      },
      utils: {
        notifyApiError(error) {
          throw error
        }
      }
    }
  }
  // Replace only the ESM network import boundary; all payment logic is unchanged.
  vm.runInNewContext(
    source.replace(
      /import\(\s*'https:\/\/esm.sh\/@getalby\/bitcoin-connect@3\.12\.3'\s*\)/,
      'Promise.resolve(window.__bitcoinConnect)'
    ),
    context
  )
  const component = context.window.PageZapGoalsPublic
  const app = component.data()
  for (const [name, method] of Object.entries(component.methods))
    app[name] = method.bind(app)
  app.goalId = 'offline-test-goal'
  app.walletPayAvailable = true
  app.amount = 21
  app.$t = key => key
  app.getGoal = async () => {
    calls.refreshed++
  }
  return {
    app,
    calls,
    sockets,
    context,
    bitcoinConnect,
    component,
    callbacks: () => callbacks
  }
}

for (const source of ['wallet', 'receiver socket', 'receiver HTTP']) {
  test(`${source} success immediately closes the modal without a preimage`, async () => {
    const {app, calls, sockets, context, callbacks} = setup()
    await app.createInvoice()
    if (source === 'wallet') callbacks().onPaid()
    else if (source === 'receiver socket')
      sockets[0].onmessage({
        data: JSON.stringify({pending: false, status: 'success'})
      })
    else {
      context.LNbits.api.request = async () => ({
        data: {paid: true, preimage: null}
      })
      await app.checkInvoiceStatus(hash)
    }
    assert.equal(calls.closed, 1)
    assert.equal(calls.refreshed, 1)
    assert.equal(calls.notifications.length, 1)
    assert.equal(app.amountDialog, false)
    assert.equal(app.invoiceDialog, false)
    assert.equal(app.invoice, null)
    assert.equal(app.bitcoinConnectPayment, null)
    assert.equal(app.invoiceSocket, null)
    assert.equal(sockets[0].closed, true)
    assert.equal(
      calls.timers.length,
      0,
      'socket close must not schedule a reconnect'
    )
  })
}

test('duplicate settlement and late wallet/cancel callbacks cannot reopen or repeat success', async () => {
  const {app, calls, sockets, callbacks} = setup()
  await app.createInvoice()
  const options = callbacks()
  const socket = sockets[0]
  options.onPaid()
  options.onPaid()
  options.onCancelled()
  socket.onmessage({data: JSON.stringify({pending: false, status: 'success'})})
  assert.equal(calls.closed, 1)
  assert.equal(calls.refreshed, 1)
  assert.equal(calls.notifications.length, 1)
  assert.equal(app.amountDialog, false)
  assert.equal(app.invoiceDialog, false)
})

test('cancellation preserves the existing amount-picker flow and ignores late success', async () => {
  const {app, calls, callbacks} = setup()
  await app.createInvoice()
  callbacks().onCancelled()
  callbacks().onPaid()
  assert.equal(app.amountDialog, true)
  assert.equal(app.invoice, null)
  assert.equal(app.invoiceSocket, null)
  assert.equal(calls.notifications.length, 0)
  assert.equal(calls.timers.length, 0)
})

test('old wallet/socket/HTTP responses cannot complete a replacement invoice', async () => {
  const {app, calls, sockets, callbacks, context} = setup()
  await app.createInvoice()
  const previous = callbacks()
  const oldSocket = sockets[0]
  let resolveStatus
  context.LNbits.api.request = () =>
    new Promise(resolve => {
      resolveStatus = resolve
    })
  const pendingStatus = app.checkInvoiceStatus(hash)
  previous.onCancelled()
  const secondHash = 'b'.repeat(64)
  context.LNbits.api.request = async () => ({
    data: {
      payment_hash: secondHash,
      payment_request: 'second-test-only-invoice'
    }
  })
  app.amount = 1
  await app.createInvoice()
  previous.onPaid()
  previous.onCancelled()
  oldSocket.onmessage({
    data: JSON.stringify({pending: false, status: 'success'})
  })
  oldSocket.onclose()
  resolveStatus({data: {paid: true}})
  await pendingStatus
  assert.equal(app.invoice?.payment_hash, secondHash)
  assert.equal(app.amountDialog, false)
  assert.equal(calls.notifications.length, 0)
  assert.equal(sockets[1].closed, false)
})

test('early receiver settlement does not open an already-paid confirmation', async () => {
  const {app, calls} = setup()
  app.watchInvoice = paymentHash => app.markPaymentComplete(paymentHash)
  await app.createInvoice()
  assert.equal(calls.launched, 0)
  assert.equal(calls.notifications.length, 1)
  assert.equal(app.creatingInvoice, false)
  assert.equal(app.invoice, null)
})

test('inline wallet success during launch leaves no stale modal handle', async () => {
  const {app, calls, bitcoinConnect} = setup()
  bitcoinConnect.launchPaymentModal = options => {
    options.onPaid()
    options.onCancelled()
    return {
      setPaid() {
        throw new Error('No preimage needed')
      }
    }
  }
  await app.createInvoice()
  assert.equal(calls.closed, 1)
  assert.equal(calls.notifications.length, 1)
  assert.equal(app.amountDialog, false)
  assert.equal(app.bitcoinConnectPayment, null)
})

test('pending/failed notifications and unrelated hashes never complete payment', async () => {
  const {app, calls, sockets, context} = setup()
  await app.createInvoice()
  for (const message of [
    {pending: true, status: 'pending'},
    {pending: false, status: 'failed'}
  ])
    sockets[0].onmessage({data: JSON.stringify(message)})
  context.LNbits.api.request = async () => ({data: {paid: false}})
  await app.checkInvoiceStatus(hash)
  app.markPaymentComplete('unrelated')
  assert.equal(app.invoice?.payment_hash, hash)
  assert.equal(calls.closed, 0)
  assert.equal(calls.notifications.length, 0)
})

test('QR-only success and manual close cleanly stop watching', async () => {
  for (const paid of [true, false]) {
    const {app, calls, sockets} = setup()
    app.walletPayAvailable = false
    await app.createInvoice()
    assert.equal(app.invoiceDialog, true)
    if (paid) app.markPaymentComplete(hash)
    else app.closeInvoice()
    assert.equal(app.invoiceDialog, false)
    assert.equal(app.invoice, null)
    assert.equal(sockets[0].closed, true)
    assert.equal(calls.closed, 0)
    assert.equal(calls.notifications.length, Number(paid))
    assert.equal(calls.timers.length, 0)
  }
})

test('queued reconnect from a cancelled invoice cannot replace the current watcher', async () => {
  const {app, sockets, calls, callbacks, context} = setup()
  await app.createInvoice()
  sockets[0].onclose()
  assert.equal(calls.timers.length, 1)
  const reconnect = calls.timers[0]
  callbacks().onCancelled()
  context.LNbits.api.request = async () => ({
    data: {
      payment_hash: 'b'.repeat(64),
      payment_request: 'second-test-only-invoice'
    }
  })
  await app.createInvoice()
  reconnect()
  assert.equal(sockets.length, 2)
  assert.equal(sockets[1].closed, false)
})

test('unmount closes the connector and ignores callbacks without notifications', async () => {
  const {app, component, calls, callbacks} = setup()
  await app.createInvoice()
  component.beforeUnmount.call(app)
  callbacks().onPaid()
  callbacks().onCancelled()
  assert.equal(calls.closed, 1)
  assert.equal(calls.notifications.length, 0)
  assert.equal(app.invoice, null)
  assert.equal(app.amountDialog, false)
})

for (const stage of ['wallet import', 'invoice request']) {
  test(`unmount during ${stage} cannot launch a late confirmation`, async () => {
    const {app, component, calls, context, bitcoinConnect} = setup()
    let resolve
    if (stage === 'wallet import')
      app.ensureBitcoinConnect = () =>
        new Promise(done => {
          resolve = () => done(bitcoinConnect)
        })
    else
      context.LNbits.api.request = () =>
        new Promise(done => {
          resolve = () =>
            done({
              data: {payment_hash: hash, payment_request: 'test-only-invoice'}
            })
        })
    const creating = app.createInvoice()
    await new Promise(resolve => setImmediate(resolve))
    component.beforeUnmount.call(app)
    resolve()
    await creating
    assert.equal(calls.launched, 0)
    assert.equal(app.invoice, null)
    assert.equal(app.creatingInvoice, false)
  })
}
