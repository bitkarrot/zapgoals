/* Safe browser regression for Python ZapGoals period-badge visibility.
 * Uses the existing sibling WASM dependencies; never installs anything:
 *   NODE_PATH=../zapgoalswasm/node_modules node ../zapgoalswasm/node_modules/@playwright/test/cli.js test tests/period-visibility.spec.cjs --workers=1 --output=/tmp/zapgoals-period-results
 * LNBITS_PERIOD_TEST_BASE_URL defaults to http://localhost:5000.
 * By default overlay repository JS/Vue/i18n/routes and embed.py string assets;
 * LNBITS_PERIOD_TEST_DEPLOYED=1 exercises installed assets instead.
 * LNBITS_PERIOD_TEST_SOURCE_REF=HEAD can demonstrate failures before the fix.
 *
 * ALL requests are intercepted BEFORE navigation. Goal saves exist only in the
 * in-memory fixture; other mutations, nonfixture APIs, external requests and
 * WebSocket sends are blocked. No credentials, browser profiles or real writes.
 * Since the authenticated admin shell returns 401 without credentials, mount
 * the ACTUAL index.js/index.vue with the host's real Vue/Quasar/i18n and LNbits
 * API client. Only its user/wallet context is mocked. Do not bypass form logic.
 */
const {test: base, expect} = require('@playwright/test')
const fs = require('node:fs')
const path = require('node:path')
const {execFileSync} = require('node:child_process')

const root = path.join(__dirname, '..')
const baseURL = (
  process.env.LNBITS_PERIOD_TEST_BASE_URL || 'http://localhost:5000'
).replace(/\/$/, '')
const origin = new URL(baseURL).origin
const goalId = 'KvdKSFTTknYKUcmxRJxr7N'
const publicPath = `/zapgoals/${goalId}`
const apiPath = '/zapgoals/api/v1/goals'
const fixtureHost = '/__period-visibility-fixture'
const repoSource = process.env.LNBITS_PERIOD_TEST_DEPLOYED !== '1'
const sourceRef = process.env.LNBITS_PERIOD_TEST_SOURCE_REF
const toggleName = 'Show period number on public page'
const wallet = {
  id: 'period-test-wallet',
  name: 'Offline period test wallet',
  inkey: 'period-test-invoice-key-NOT-REAL',
  adminkey: 'period-test-admin-key-NOT-REAL',
  balance: 0
}
const targetWallet = {
  ...wallet,
  id: 'period-test-target',
  name: 'Offline target'
}
const fixture = {
  id: goalId,
  wallet: wallet.id,
  title: 'Offline period visibility regression',
  description_above: '',
  description_below: '',
  current_amount: 100,
  goal_amount: 1000,
  percent: 10,
  status: 'active',
  suggested_amounts: [21, 100, 500, 1000],
  target_date: '2099-01-01T00:00:00Z',
  wallet_mode: 'vanilla',
  recurring: true,
  period_index: 2,
  recurrence_unit: 'month',
  recurrence_interval: 1,
  recurrence_day_of_month: 1,
  target_wallet_id: targetWallet.id,
  rollover_mode: 'counts_as_progress',
  sweep_mode: 'target_amount',
  background_color: '#ffffff',
  text_color: '#1f2937',
  progress_color: '#f59e0b',
  remainder_color: '#e5e7eb',
  font_family: 'sans-serif',
  font_name: 'sans-serif',
  font_weight: 400,
  nostr_pubkey: null,
  lightning_address_username: null
}
const scheduleFields = [
  'recurring',
  'recurrence_unit',
  'recurrence_interval',
  'recurrence_day_of_month',
  'target_wallet_id',
  'target_date',
  'rollover_mode',
  'sweep_mode'
]
const clone = value => JSON.parse(JSON.stringify(value))
const schedule = value =>
  Object.fromEntries(
    scheduleFields.map(key => [
      key,
      key === 'target_date' ? new Date(value[key]).toISOString() : value[key]
    ])
  )
function readSource(relative) {
  return sourceRef
    ? execFileSync('git', ['show', `${sourceRef}:${relative}`], {
        cwd: root,
        encoding: 'utf8'
      })
    : fs.readFileSync(path.join(root, relative), 'utf8')
}
// Parse ONLY Python string constants. No importing app modules, FastAPI, LNbits,
// settings, DB, or executing embed.py, even when deployed service is pre-migration.
const embeds = repoSource
  ? JSON.parse(
      execFileSync(
        'python3',
        [
          '-c',
          'import ast,json,sys; tree=ast.parse(sys.stdin.read()); print(json.dumps({n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ("EMBED_HTML","WIDGET_JS")}))'
        ],
        {input: readSource('embed.py'), encoding: 'utf8'}
      )
    )
  : null

const test = base.extend({
  harness: async ({page, context}, use) => {
    const network = {
      goal: clone(fixture),
      goals: [],
      allowGoalSaves: false,
      saves: [],
      blockedMutations: [],
      blockedReads: [],
      publicReads: 0,
      assets: [],
      apiKeys: []
    }
    const pageErrors = []
    page.on('pageerror', error => {
      const stack = error.stack || error.message
      // LNbits assumes SW registration exists. Blocking workers intentionally
      // causes this unrelated core exception; no extension errors are ignored.
      if (
        error.message ===
          "Cannot read properties of undefined (reading 'scope')" &&
        stack.includes(`${origin}/static/bundle.min.js`)
      )
        return
      pageErrors.push(stack)
    })
    const json = (route, value, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(value)
      })
    await context.route('**/*', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const method = request.method()
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        if (
          network.allowGoalSaves &&
          url.origin === origin &&
          ((method === 'POST' && url.pathname === apiPath) ||
            (method === 'PUT' && url.pathname === `${apiPath}/${goalId}`))
        ) {
          const key = request.headers()['x-api-key']
          network.apiKeys.push(key)
          if (key !== wallet.adminkey)
            return json(route, {detail: 'Only fixture keys permitted'}, 403)
          const body = request.postDataJSON()
          network.saves.push({method, body: clone(body)})
          // Echo rather than normalize the bool: test must catch omitted fields,
          // false converted to true, and string values in the actual payload.
          const saved = {...clone(fixture), ...body, id: goalId}
          network.goals = [saved]
          network.goal = clone(saved)
          return json(route, saved)
        }
        network.blockedMutations.push(`${method} ${url.origin}${url.pathname}`)
        return json(
          route,
          {detail: 'Mutation blocked by offline regression'},
          403
        )
      }
      if (url.origin !== origin) return route.abort('blockedbyclient')
      if (url.pathname === `${apiPath}/${goalId}/public`) {
        network.publicReads++
        return json(route, network.goal)
      }
      if (url.pathname === apiPath) {
        network.apiKeys.push(request.headers()['x-api-key'])
        return json(route, network.goals)
      }
      if (url.pathname === '/zapgoals/api/v1/recurring/scheduler-status') {
        network.apiKeys.push(request.headers()['x-api-key'])
        return json(route, {
          builtin_scheduler: true,
          scheduler_extension: false,
          scheduler_frequency: 'daily'
        })
      }
      if (url.pathname.includes('/api/')) {
        network.blockedReads.push(url.pathname)
        return json(route, {detail: 'Nonfixture API blocked'}, 403)
      }
      if (url.pathname === `${fixtureHost}/iframe`) {
        return route.fulfill({
          contentType: 'text/html',
          body: `<!doctype html><html lang="en"><title>Offline iframe host</title><iframe title="ZapGoals test embed" src="${publicPath}/embed" style="width:600px;height:800px;border:0"></iframe></html>`
        })
      }
      if (url.pathname === `${fixtureHost}/widget`) {
        return route.fulfill({
          contentType: 'text/html',
          body: `<!doctype html><html lang="en"><head><title>Offline widget host</title></head><body><script src="/zapgoals/embed.js" data-goal="${goalId}"></script></body></html>`
        })
      }
      if (url.pathname === `${publicPath}/embed`) {
        network.assets.push(url.pathname)
        if (repoSource)
          return route.fulfill({
            contentType: 'text/html',
            body: embeds.EMBED_HTML
          })
      }
      if (url.pathname === '/zapgoals/embed.js') {
        network.assets.push(url.pathname)
        if (repoSource)
          return route.fulfill({
            contentType: 'application/javascript',
            body: embeds.WIDGET_JS.trim()
          })
      }
      const asset = url.pathname.match(
        /^\/zapgoals\/(static\/(?:routes\.json|js\/(?:index\.(?:js|vue)|public\.(?:js|vue)|i18n\/en\.js)))$/
      )
      if (asset) {
        network.assets.push(url.pathname)
        if (repoSource)
          return route.fulfill({
            contentType: asset[1].endsWith('.js')
              ? 'application/javascript'
              : asset[1].endsWith('.json')
                ? 'application/json'
                : 'text/plain',
            body: readSource(asset[1])
          })
      }
      return route.continue()
    })
    await context.addInitScript(() => {
      window.__periodVisibilityTest = {sockets: [], socketSends: []}
      // An isolated context has no keys/cookies. Mock live updates as well so
      // unrelated real events can never overwrite the public fixture.
      window.WebSocket = class {
        constructor(url) {
          this.__v_skip = true
          this.url = String(url)
          this.readyState = 0
          window.__periodVisibilityTest.sockets.push(this)
          setTimeout(() => {
            if (this.readyState !== 0) return
            this.readyState = 1
            this.onopen?.()
          }, 0)
        }
        close() {
          this.readyState = 3
          this.onclose?.()
        }
        send(value) {
          window.__periodVisibilityTest.socketSends.push(value)
          throw new Error('WebSocket mutations blocked by offline regression')
        }
        static OPEN = 1
        static CLOSED = 3
      }
    })
    await use({page, network})
    expect(
      network.blockedMutations,
      'No attempted payment/scheduler/other writes'
    ).toEqual([])
    expect(
      network.apiKeys.every(key =>
        [wallet.inkey, wallet.adminkey].includes(key)
      ),
      'All API keys must be fake fixture keys'
    ).toBe(true)
    for (const frame of page.frames()) {
      if (!frame.isDetached()) {
        expect(
          await frame.evaluate(
            () => window.__periodVisibilityTest?.socketSends || []
          )
        ).toEqual([])
      }
    }
    expect(pageErrors, 'No extension runtime errors').toEqual([])
  }
})

test.use({viewport: {width: 1280, height: 1000}, serviceWorkers: 'block'})
test.setTimeout(30000)

async function openPublic({page, network}) {
  await page.goto(`${baseURL}${publicPath}`)
  await expect(
    page.getByRole('heading', {name: network.goal.title})
  ).toBeVisible()
  await expect(
    page.getByRole('progressbar', {name: 'Progress', exact: true})
  ).toHaveAttribute('aria-valuenow', '10')
  await expect(
    page.getByRole('button', {name: 'Zap this goal', exact: true})
  ).toBeVisible()
  expect(network.publicReads).toBeGreaterThan(0)
  expect(network.assets).toContain('/zapgoals/static/js/public.vue')
}

async function mountAdmin(harness) {
  const {page, network} = harness
  network.allowGoalSaves = true
  await openPublic(harness)
  await page.evaluate(async () => {
    const response = await fetch('/zapgoals/static/js/index.vue')
    if (!response.ok) throw new Error('Cannot load actual admin template')
    document.body.insertAdjacentHTML('beforeend', await response.text())
  })
  await page.addScriptTag({url: `${baseURL}/zapgoals/static/js/i18n/en.js`})
  await page.addScriptTag({url: `${baseURL}/zapgoals/static/js/index.js`})
  await page.evaluate(
    ({wallet, targetWallet}) => {
      // Preserve host globals, API client, translations and Quasar components.
      // Only the otherwise authenticated admin context is synthetic.
      document.getElementById('vue').style.display = 'none'
      const host = document.createElement('main')
      host.id = 'period-visibility-admin'
      document.body.appendChild(host)
      const admin = Vue.createApp(window.PageZapGoals)
      admin.use(Quasar)
      admin.use(window.i18n)
      admin.mixin({
        data: () => ({
          g: {
            user: {id: 'offline-period-user', wallets: [wallet, targetWallet]}
          }
        })
      })
      window.__periodVisibilityTest.admin = admin.mount(host)
    },
    {wallet, targetWallet}
  )
  await expect(
    page.getByRole('button', {name: 'New goal', exact: true})
  ).toBeVisible()
  await expect
    .poll(() =>
      page.evaluate(() => window.__periodVisibilityTest.admin.loading)
    )
    .toBe(false)
  expect(network.assets).toEqual(
    expect.arrayContaining([
      '/zapgoals/static/js/index.js',
      '/zapgoals/static/js/index.vue',
      '/zapgoals/static/js/i18n/en.js'
    ])
  )
}

const variants = [
  {name: 'legacy missing flag defaults visible', fields: {}, visible: true},
  {
    name: 'explicit true is visible',
    fields: {show_period_badge: true},
    visible: true
  },
  {
    name: 'explicit false is hidden',
    fields: {show_period_badge: false},
    visible: false
  },
  {
    name: 'nonrecurring true is hidden',
    fields: {recurring: false, show_period_badge: true},
    visible: false
  },
  {
    name: 'nonrecurring missing flag is hidden',
    fields: {recurring: false},
    visible: false
  }
]
for (const variant of variants) {
  test(`public: ${variant.name}`, async ({harness}) => {
    Object.assign(harness.network.goal, variant.fields)
    await openPublic(harness)
    const badge = harness.page.getByText('Period 3', {exact: true})
    if (variant.visible) await expect(badge).toBeVisible()
    else await expect(badge).toHaveCount(0)
    expect(harness.network.saves).toEqual([])
  })
  for (const surface of ['iframe', 'widget']) {
    test(`${surface}: ${variant.name}`, async ({harness}) => {
      const {page, network} = harness
      Object.assign(network.goal, variant.fields)
      await page.goto(`${baseURL}${fixtureHost}/${surface}`)
      const view =
        surface === 'iframe'
          ? page.frameLocator('iframe[title="ZapGoals test embed"]')
          : page.locator('.zapgoals-widget-container') // locators pierce real shadow DOM
      await expect(view.locator('.zg-title')).toHaveText(fixture.title)
      const badge = view.locator('.zg-recurring-badge')
      if (variant.visible) {
        await expect(badge).toBeVisible()
        await expect(badge).toContainText('Period 3')
      } else {
        await expect(badge).toHaveCount(0)
      }
      await expect(view.locator('.zg-percent')).toContainText('10')
      await expect(view.locator('.zg-zap-btn')).toBeVisible()
      expect(network.publicReads).toBeGreaterThan(0)
      expect(network.assets).toContain(
        surface === 'iframe' ? `${publicPath}/embed` : '/zapgoals/embed.js'
      )
      expect(network.saves).toEqual([])
    })
  }
}

async function openEdit(page) {
  await page.getByRole('button', {name: 'Edit goal', exact: true}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
}
async function saveAndCheck(harness, expected, method = 'PUT') {
  const {page, network} = harness
  const before = network.saves.length
  await page.getByRole('button', {name: 'Save goal', exact: true}).click()
  await expect.poll(() => network.saves.length).toBe(before + 1)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  const save = network.saves.at(-1)
  expect(save.method).toBe(method)
  expect(save.body.show_period_badge).toBe(expected)
  expect(typeof save.body.show_period_badge).toBe('boolean')
  return save.body
}

test('admin: new goals default true; real toggle creates false and reopens false', async ({
  harness
}) => {
  const {page, network} = harness
  await mountAdmin(harness)
  await page.getByRole('button', {name: 'New goal', exact: true}).click()
  expect(
    await page.evaluate(
      () =>
        window.__periodVisibilityTest.admin.formDialog.data.show_period_badge
    )
  ).toBe(true)
  await expect(
    page.getByRole('switch', {name: toggleName, exact: true})
  ).toHaveCount(0)
  await page
    .getByRole('textbox', {name: 'Title *', exact: true})
    .fill('Created offline period goal')
  await page.getByRole('switch', {name: 'Recurring goal', exact: true}).click()
  const toggle = page.getByRole('switch', {name: toggleName, exact: true})
  await expect(toggle).toBeChecked()
  await expect(
    page.getByText(/without changing the recurring schedule or period history/)
  ).toBeVisible()
  // Fill the normal required schedule controls, without replacing saveGoal or
  // its validator. The displayed datetime-local input accepts a local value.
  await page.locator('input[type="datetime-local"]').fill('2099-01-01T00:00')
  await page
    .getByRole('combobox', {name: 'Target wallet for sweeps *', exact: true})
    .click()
  await page.getByRole('option', {name: targetWallet.name, exact: true}).click()
  await toggle.click()
  await expect(toggle).not.toBeChecked()
  const body = await saveAndCheck(harness, false, 'POST')
  expect(body.recurring).toBe(true)
  expect(body.target_wallet_id).toBe(targetWallet.id)
  await openEdit(page)
  await expect(toggle).not.toBeChecked()
  expect(network.saves).toHaveLength(1)
})

for (const initial of [false, true, undefined]) {
  test(`admin: edit ${String(initial)} preserves value across save/reload/reopen; toggling is display-only`, async ({
    harness
  }) => {
    const {page, network} = harness
    const goal = clone(fixture)
    if (initial !== undefined) goal.show_period_badge = initial
    network.goals = [goal]
    await mountAdmin(harness)
    await openEdit(page)
    const toggle = page.getByRole('switch', {name: toggleName, exact: true})
    const expected = initial !== false
    await expect(toggle).toBeChecked({checked: expected})
    const before = schedule(goal)
    const unchanged = await saveAndCheck(harness, expected)
    expect(schedule(unchanged)).toEqual(before)
    // Fetch through the REAL component/API client to verify reopening from API
    // data, rather than merely retaining local dialog state.
    await page.evaluate(() => window.__periodVisibilityTest.admin.getGoals())
    await openEdit(page)
    await expect(toggle).toBeChecked({checked: expected})
    await toggle.click()
    await expect(toggle).toBeChecked({checked: !expected})
    const changed = await saveAndCheck(harness, !expected)
    expect(schedule(changed)).toEqual(before)
    await page.evaluate(() => window.__periodVisibilityTest.admin.getGoals())
    await openEdit(page)
    await expect(toggle).toBeChecked({checked: !expected})
    expect(network.saves).toHaveLength(2)
    await openPublic(harness)
    const badge = page.getByText('Period 3', {exact: true})
    if (!expected) await expect(badge).toBeVisible()
    else await expect(badge).toHaveCount(0)
  })
}
