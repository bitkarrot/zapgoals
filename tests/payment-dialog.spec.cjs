/* Safe regression for the Python public page with the REAL Bitcoin Connect UI.
 * Reuse existing Playwright/esbuild (no dependency install):
 *   NODE_PATH=../zapgoalswasm/node_modules node ../zapgoalswasm/node_modules/@playwright/test/cli.js test tests/payment-dialog.spec.cjs --workers=1
 * Optional LNBITS_PAYMENT_TEST_SOURCE_REF=HEAD tests an earlier public.js;
 * LNBITS_PAYMENT_TEST_DEPLOYED=1 tests installed assets; BASE_URL defaults local.
 * ALL mutations are intercepted BEFORE navigation; invoice/provider fixtures
 * are offline-only. Never use an existing browser profile or real wallet key.
 */
const {test: base, expect} = require('@playwright/test')
const {buildSync} = require('esbuild')
const fs = require('node:fs')
const path = require('node:path')
const {execFileSync} = require('node:child_process')

const baseURL = (
  process.env.LNBITS_PAYMENT_TEST_BASE_URL || 'http://localhost:5000'
).replace(/\/$/, '')
const goalId =
  process.env.LNBITS_PAYMENT_TEST_GOAL_ID || 'KvdKSFTTknYKUcmxRJxr7N'
const origin = new URL(baseURL).origin
const repoSource = process.env.LNBITS_PAYMENT_TEST_DEPLOYED !== '1'
const source = !repoSource
  ? null
  : process.env.LNBITS_PAYMENT_TEST_SOURCE_REF
    ? execFileSync(
        'git',
        [
          'show',
          `${process.env.LNBITS_PAYMENT_TEST_SOURCE_REF}:static/js/public.js`
        ],
        {cwd: path.join(__dirname, '..'), encoding: 'utf8'}
      )
    : fs.readFileSync(path.join(__dirname, '../static/js/public.js'), 'utf8')
const moduleURL = 'https://esm.sh/@getalby/bitcoin-connect@3.12.3'
const bcPackage = path.join(
  path.dirname(require.resolve('@getalby/bitcoin-connect')),
  '../package.json'
)
if (JSON.parse(fs.readFileSync(bcPackage, 'utf8')).version !== '3.12.3')
  throw new Error('Use the same Bitcoin Connect 3.12.3 as the public page')
// Fulfil the real dynamic ESM import using the installed, same-version package,
// avoiding CDN availability while retaining the real modal and LNbits connector.
const bcBundle = buildSync({
  stdin: {
    contents: `import * as bc from '@getalby/bitcoin-connect';
    export * from '@getalby/bitcoin-connect';
    export function launchPaymentModal(options) {
      window.__paymentDialogTest.callbacks.push(options);
      return bc.launchPaymentModal(options);
    }`,
    resolveDir: path.dirname(bcPackage)
  },
  bundle: true,
  write: false,
  format: 'esm',
  platform: 'browser',
  target: 'es2020',
  external: ['crypto']
}).outputFiles[0].text
const amount = 21
const preimage = '01'.repeat(32)
const paymentHash =
  '72cd6e8422c407fb6d098690f1130b7ded7ec2f7f5e1d30bd9d521f015363793'
// Signed OFFLINE (03*32 key, 01*32 preimage, 02*32 secret), never LNbits-created.
// Timestamp 1788825600; expiry 315360000. NEVER pay this test-only fixture.
const paymentRequest =
  'lnbc210n1p4f75qqpp5wtxkappzcsrlkmgfs6g0zyct0hkhashh7hsaxz7e65slq9fkx7fssp5qgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqdpafanxvmrfdejjqun9vaex2umnd9hkugrxd9u8gatjv5sz6gzwg4ty253q2pq4jxqxfvcqcqn7hhv4vpa36t58ufc0my5a2qs90u79cvc0d0lqv76qn5fqcwaaqsptk2rgn6u8wyx8rkdwtrqmhc5yk9n28dadszwz4y3as8ynq6yccpdat4lu'
const goal = {
  id: goalId,
  title: 'Python payment dialog regression fixture',
  description_above: '',
  description_below: '',
  current_amount: 100,
  goal_amount: 1000,
  percent: 10,
  status: 'active',
  suggested_amounts: [21, 100, 500, 1000],
  target_date: '2099-01-01T00:00:00Z',
  wallet_mode: 'all',
  recurring: false
}

const test = base.extend({
  harness: async ({page, context}, use) => {
    const network = {
      mode: 'success',
      receiverPaid: false,
      currentAmount: 100,
      invoices: [],
      payments: [],
      lookups: [],
      wallets: [],
      blocked: [],
      scripts: []
    }
    const pageErrors = []
    page.on('pageerror', error => {
      const stack = error.stack || error.message
      // The host assumes service-worker registration exists; blocking workers
      // for safe request interception triggers this unrelated core error.
      if (
        error.message ===
          "Cannot read properties of undefined (reading 'scope')" &&
        stack.includes(`${origin}/static/bundle.min.js`)
      )
        return
      pageErrors.push(stack)
    })
    const json = (route, body, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body)
      })
    await context.route('**/*', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const method = request.method()
      // Every invoice/payment POST on ANY origin is mocked. All other mutations
      // are blocked, including accidental goal/admin/backend operations.
      if (
        method === 'POST' &&
        url.pathname === `/zapgoals/api/v1/goals/${goalId}/invoice`
      ) {
        network.invoices.push(request.postDataJSON())
        return json(route, {
          payment_hash: paymentHash,
          payment_request: paymentRequest
        })
      }
      if (method === 'POST' && /^\/api\/v1\/payments\/?$/.test(url.pathname)) {
        network.payments.push({
          body: request.postDataJSON(),
          testKey: request.headers()['x-api-key'] === 'test-only',
          origin: url.origin
        })
        if (network.mode === 'payer-error')
          return json(route, {detail: 'Test-only payer failure'}, 500)
        network.currentAmount += amount
        return json(route, {
          payment_hash: paymentHash,
          payment_request: paymentRequest
        })
      }
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        network.blocked.push(`${method} ${url.origin}${url.pathname}`)
        return json(
          route,
          {detail: 'Blocked unexpected mutation by regression test'},
          403
        )
      }
      if (method === 'GET' && url.pathname.startsWith('/api/v1/payments/')) {
        const payer = request.headers()['x-api-key'] === 'test-only'
        network.lookups.push({payer, pathname: url.pathname})
        return json(route, {
          payment_hash: paymentHash,
          paid: payer || network.receiverPaid,
          pending: !payer && !network.receiverPaid,
          status: payer || network.receiverPaid ? 'success' : 'pending',
          preimage: payer && network.mode === 'success' ? preimage : null
        })
      }
      if (method === 'GET' && url.pathname === '/api/v1/wallet') {
        network.wallets.push({
          testKey: request.headers()['x-api-key'] === 'test-only'
        })
        return json(route, {
          id: 'test-only-wallet',
          name: 'Offline regression wallet',
          balance: 100000000
        })
      }
      if (
        method === 'GET' &&
        url.pathname === `/zapgoals/api/v1/goals/${goalId}/public`
      )
        return json(route, {
          ...goal,
          current_amount: network.currentAmount,
          percent: network.currentAmount / 10
        })
      if (url.href === moduleURL)
        return route.fulfill({
          contentType: 'application/javascript',
          headers: {'access-control-allow-origin': '*'},
          body: bcBundle
        })
      if (url.pathname === '/zapgoals/static/js/public.js') {
        network.scripts.push(url.pathname + url.search)
        if (repoSource)
          return route.fulfill({
            contentType: 'application/javascript',
            body: source
          })
      }
      if (repoSource && url.pathname === '/zapgoals/static/js/public.vue')
        return route.fulfill({
          contentType: 'text/plain',
          body: fs.readFileSync(
            path.join(__dirname, '../static/js/public.vue'),
            'utf8'
          )
        })
      if (url.origin !== origin) return route.abort('blockedbyclient')
      return route.continue()
    })
    await context.addInitScript(() => {
      const state = (window.__paymentDialogTest = {
        callbacks: [],
        sockets: [],
        notifications: []
      })
      let component
      Object.defineProperty(window, 'PageZapGoalsPublic', {
        configurable: true,
        get: () => component,
        set(value) {
          component = value
          const created = value.created
          value.created = function () {
            state.app = this
            return created.call(this)
          }
        }
      })
      // Receiver subscriptions are mocked too: no live events can influence tests.
      window.WebSocket = class {
        constructor(url) {
          // Like a native WebSocket, this identity must not be Vue-proxied.
          this.__v_skip = true
          this.url = url
          this.readyState = 0
          state.sockets.push(this)
          setTimeout(() => {
            if (this.readyState === 0) {
              this.readyState = 1
              this.onopen?.()
            }
          }, 0)
        }
        close() {
          this.readyState = 3
          this.onclose?.()
        }
        send() {
          throw new Error('Unexpected WebSocket mutation')
        }
        static OPEN = 1
        static CLOSED = 3
      }
    })
    await page.goto(`${baseURL}/zapgoals/${encodeURIComponent(goalId)}`)
    await expect(page.getByRole('heading', {name: goal.title})).toBeVisible()
    await page.evaluate(async moduleURL => {
      const state = window.__paymentDialogTest
      const notify = Quasar.Notify.create
      Quasar.Notify.create = options => {
        state.notifications.push(options)
        return notify(options)
      }
      const bc = (state.bc = await import(moduleURL))
      bc.init({
        appName: 'ZapGoals',
        showBalance: false,
        persistConnection: false
      })
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error('Mock LNbits connector did not connect')),
          5000
        )
        const unsubscribe = bc.onConnected(() => {
          clearTimeout(timeout)
          unsubscribe()
          resolve()
        })
        bc.connect({
          connectorType: 'lnbits',
          connectorName: 'LNbits',
          lnbitsInstanceUrl: location.origin,
          lnbitsAdminKey: 'test-only'
        })
      })
    }, moduleURL)
    await use({page, network})
    if (!repoSource) {
      expect(network.scripts).toHaveLength(1)
      expect(
        network.scripts[0],
        'Extension revision must survive LNbits overriding v'
      ).toContain('rev=0.1.6')
    }
    expect(
      network.blocked,
      'No unmocked mutation may reach the server'
    ).toEqual([])
    expect(
      network.payments.every(
        payment => payment.testKey && payment.origin === origin
      )
    ).toBe(true)
    expect(network.wallets.every(wallet => wallet.testKey)).toBe(true)
    expect(pageErrors).toEqual([])
  }
})

test.use({viewport: {width: 1280, height: 900}, serviceWorkers: 'block'})
test.setTimeout(30000)

async function openPayment({page, network}) {
  await page.getByRole('button', {name: 'Zap this goal', exact: true}).click()
  await page.getByRole('button', {name: String(amount), exact: true}).click()
  const confirm = page.getByRole('button', {name: /Confirm Payment/})
  await expect(confirm).toBeVisible()
  await expect(page.locator('bc-modal')).toHaveCount(1)
  expect(network.invoices).toEqual([{amount, comment: null}])
  return confirm
}

async function expectPaid({page}) {
  await expect(
    page.locator('bc-modal'),
    'Real Confirm Payment must close immediately'
  ).toHaveCount(0, {timeout: 750})
  await expect(
    page.getByText('Payment received. Thank you!', {exact: true})
  ).toBeVisible()
  await expect(page.locator('.zapgoals-amount-dialog')).toHaveCount(0)
  expect(
    await page.evaluate(() => {
      const state = window.__paymentDialogTest
      return {
        invoice: state.app.invoice,
        modal: state.app.bitcoinConnectPayment,
        socket: state.app.invoiceSocket,
        amountDialog: state.app.amountDialog,
        invoiceDialog: state.app.invoiceDialog,
        notifications: state.notifications.filter(n => n.type === 'positive')
          .length
      }
    })
  ).toEqual({
    invoice: null,
    modal: null,
    socket: null,
    amountDialog: false,
    invoiceDialog: false,
    notifications: 1
  })
}

async function emitSettlement(page) {
  await page.evaluate(paymentHash => {
    const socket = window.__paymentDialogTest.sockets.findLast(socket =>
      socket.url.endsWith('/' + paymentHash)
    )
    socket.onmessage({
      data: JSON.stringify({pending: false, status: 'success'})
    })
  }, paymentHash)
}

test('real Confirm Payment closes immediately on provider success', async ({
  harness
}) => {
  const {page, network} = harness
  const confirm = await openPayment(harness)
  await confirm.click()
  await expectPaid(harness)
  expect(network.payments.map(payment => payment.body)).toEqual([
    {bolt11: paymentRequest, out: true}
  ])
  await expect
    .poll(() =>
      page.evaluate(() => window.__paymentDialogTest.app.goal.current_amount)
    )
    .toBe(121)
})

for (const mode of ['missing-preimage', 'payer-error']) {
  test(`receiver settlement closes Confirm Payment after ${mode}`, async ({
    harness
  }) => {
    const {page, network} = harness
    network.mode = mode
    const confirm = await openPayment(harness)
    await confirm.click()
    await expect(
      page.getByText(
        mode === 'missing-preimage' ? 'No preimage' : 'Test-only payer failure',
        {exact: true}
      )
    ).toBeVisible()
    await expect(page.locator('bc-modal')).toHaveCount(1)
    const lookups = network.lookups.length
    await emitSettlement(page)
    await expectPaid(harness)
    expect(
      network.lookups,
      'Receiver settlement must not fetch preimages'
    ).toHaveLength(lookups)
    expect(network.payments).toHaveLength(1)
  })
}

test('independent paid HTTP status closes the real modal without a preimage', async ({
  harness
}) => {
  const {page, network} = harness
  await openPayment(harness)
  network.receiverPaid = true
  await page.evaluate(
    paymentHash =>
      window.__paymentDialogTest.app.checkInvoiceStatus(paymentHash),
    paymentHash
  )
  await expectPaid(harness)
  expect(network.payments).toHaveLength(0)
})

test('manual cancellation restores the amount picker without reporting success', async ({
  harness
}) => {
  const {page, network} = harness
  await openPayment(harness)
  await page.locator('bc-modal-header').getByRole('button').last().click()
  await expect(page.locator('bc-modal')).toHaveCount(0)
  await expect(page.getByText('Choose your zap', {exact: true})).toBeVisible()
  expect(
    await page.evaluate(() => ({
      invoice: window.__paymentDialogTest.app.invoice,
      notifications: window.__paymentDialogTest.notifications
    }))
  ).toEqual({invoice: null, notifications: []})
  expect(network.payments).toHaveLength(0)
})

test('late paid/cancel/socket callbacks cannot reopen success or complete the next invoice', async ({
  harness
}) => {
  const {page} = harness
  const confirm = await openPayment(harness)
  await confirm.click()
  await expectPaid(harness)
  await page.evaluate(() => {
    const state = window.__paymentDialogTest
    state.callbacks[0].onPaid()
    state.callbacks[0].onCancelled()
  })
  await emitSettlement(page)
  await expectPaid(harness)
  await page.getByRole('button', {name: 'Zap this goal', exact: true}).click()
  // A replacement hash distinguishes callbacks already queued for the old invoice.
  await page.evaluate(() => {
    const state = window.__paymentDialogTest
    state.app.invoice = {
      payment_hash: 'b'.repeat(64),
      payment_request: 'offline-second-invoice'
    }
    state.app.paymentState = 'pending'
    state.callbacks[0].onPaid()
    state.callbacks[0].onCancelled()
  })
  await emitSettlement(page)
  expect(
    await page.evaluate(() => ({
      hash: window.__paymentDialogTest.app.invoice?.payment_hash,
      count: window.__paymentDialogTest.notifications.filter(
        n => n.type === 'positive'
      ).length
    }))
  ).toEqual({hash: 'b'.repeat(64), count: 1})
})

test('early settlement never launches an already-paid confirmation', async ({
  harness
}) => {
  const {page, network} = harness
  await page.evaluate(() => {
    const app = window.__paymentDialogTest.app
    app.watchInvoice = hash => app.markPaymentComplete(hash)
  })
  await page.getByRole('button', {name: 'Zap this goal', exact: true}).click()
  await page.getByRole('button', {name: String(amount), exact: true}).click()
  await expectPaid(harness)
  expect(
    await page.evaluate(() => window.__paymentDialogTest.callbacks.length)
  ).toBe(0)
  expect(network.payments).toHaveLength(0)
})

test('QR-only receiver settlement still completes and closes its dialog', async ({
  harness
}) => {
  const {page, network} = harness
  await page.evaluate(() => {
    window.__paymentDialogTest.app.goal.wallet_mode = 'vanilla'
  })
  await page.getByRole('button', {name: 'Zap this goal', exact: true}).click()
  await page.getByRole('button', {name: String(amount), exact: true}).click()
  await page
    .getByRole('button', {name: `Zap ${amount} sats`, exact: true})
    .click()
  await expect(page.getByLabel('BOLT11 invoice')).toHaveValue(paymentRequest)
  await emitSettlement(page)
  await expectPaid(harness)
  await expect(page.getByLabel('BOLT11 invoice')).toHaveCount(0)
  expect(network.payments).toHaveLength(0)
})
