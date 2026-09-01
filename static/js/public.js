window.PageZapGoalsPublic = {
  template: '#page-zapgoals-public',
  data() {
    return {
      goalId: null,
      goal: null,
      loading: true,
      loadError: '',
      amount: null,
      comment: '',
      amountDialog: false,
      creatingInvoice: false,
      invoiceDialog: false,
      invoice: null,
      goalSocket: null,
      invoiceSocket: null,
      goalReconnectTimer: null,
      invoiceReconnectTimer: null,
      goalReconnectAttempt: 0,
      invoiceReconnectAttempt: 0,
      countdownTimer: null,
      now: Date.now(),
      destroyed: false
    }
  },
  computed: {
    cardStyle() {
      return {
        backgroundColor: this.goal?.background_color || '#ffffff',
        color: this.goal?.text_color || '#1f2937',
        fontFamily: this.goal?.font_family || 'sans-serif'
      }
    },
    trackStyle() {
      return {backgroundColor: this.goal?.remainder_color || '#e5e7eb'}
    },
    fillStyle() {
      return {
        width: `${this.cappedPercent}%`,
        backgroundColor: this.goal?.progress_color || '#f59e0b'
      }
    },
    actionStyle() {
      const backgroundColor = this.goal?.progress_color || '#f59e0b'
      return {
        backgroundColor,
        color: this.contrastColor(backgroundColor)
      }
    },
    actualPercent() {
      if (this.goal?.percent !== undefined && this.goal?.percent !== null) {
        return Number(this.goal.percent) || 0
      }
      const target = Number(this.goal?.goal_amount) || 0
      return target
        ? (Number(this.goal?.current_amount || 0) / target) * 100
        : 0
    },
    cappedPercent() {
      return Math.min(100, Math.max(0, this.actualPercent))
    },
    percentLabel() {
      const value = this.actualPercent
      return `${value >= 1000 ? value.toLocaleString(undefined, {maximumFractionDigits: 1}) : value.toFixed(1)}%`
    },
    walletPayAvailable() {
      return this.goal?.wallet_mode === 'all'
    },
    suggestedAmounts() {
      return (this.goal?.suggested_amounts || [21, 100, 500, 1000]).slice(0, 4)
    },
    lnurlUrl() {
      return this.goal?.lnurl_url || this.goal?.lnurl || ''
    },
    targetLabel() {
      if (!this.goal?.target_date) return '—'
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'long',
        timeStyle: 'short'
      }).format(new Date(this.goal.target_date))
    },
    countdownLabel() {
      if (!this.goal) return ''
      if (Number(this.goal.current_amount) >= Number(this.goal.goal_amount)) {
        return this.$t('zapgoals.goal_reached')
      }
      const difference = new Date(this.goal.target_date).getTime() - this.now
      if (difference <= 0) return this.goal.status || this.$t('zapgoals.ended')
      const days = Math.floor(difference / 86400000)
      const hours = Math.floor((difference % 86400000) / 3600000)
      const minutes = Math.floor((difference % 3600000) / 60000)
      const seconds = Math.floor((difference % 60000) / 1000)
      if (days) return this.$t('zapgoals.countdown_days', {days, hours})
      if (hours) return this.$t('zapgoals.countdown_hours', {hours, minutes})
      return this.$t('zapgoals.countdown_minutes', {minutes, seconds})
    }
  },
  async created() {
    this.goalId = this.$route.params.id
    await this.getGoal()
    this.connectGoalSocket()
    this.countdownTimer = window.setInterval(() => {
      this.now = Date.now()
    }, 1000)
  },
  beforeUnmount() {
    this.destroyed = true
    window.clearInterval(this.countdownTimer)
    window.clearTimeout(this.goalReconnectTimer)
    window.clearTimeout(this.invoiceReconnectTimer)
    if (this.goalSocket) this.goalSocket.close()
    if (this.invoiceSocket) this.invoiceSocket.close()
  },
  methods: {
    async getGoal(silent = false) {
      if (!silent) this.loading = true
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/zapgoals/api/v1/goals/${this.goalId}/public`
        )
        this.goal = data
        this.loadError = ''
      } catch (error) {
        this.loadError = this.$t('zapgoals.public_load_error')
        if (!silent) LNbits.utils.notifyApiError(error)
      } finally {
        this.loading = false
      }
    },
    websocketUrl(path) {
      const url = new URL(window.location.origin)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      url.pathname = path
      return url.toString()
    },
    connectGoalSocket() {
      if (this.destroyed || !this.goalId) return
      if (this.goalSocket) this.goalSocket.close()
      const socket = new WebSocket(
        this.websocketUrl(`/api/v1/ws/${this.goalId}`)
      )
      this.goalSocket = socket
      socket.onopen = () => {
        this.goalReconnectAttempt = 0
      }
      socket.onmessage = () => {
        this.getGoal(true)
      }
      socket.onerror = () => socket.close()
      socket.onclose = () => {
        if (this.goalSocket !== socket) return
        this.goalSocket = null
        if (this.destroyed) return
        const delay = Math.min(10000, 1000 * 2 ** this.goalReconnectAttempt)
        this.goalReconnectAttempt = Math.min(this.goalReconnectAttempt + 1, 4)
        this.goalReconnectTimer = window.setTimeout(
          () => this.connectGoalSocket(),
          delay
        )
      }
    },
    openAmountDialog() {
      this.amount = null
      this.comment = ''
      this.amountDialog = true
    },
    async selectSuggestedAmount(amount) {
      this.amount = Number(amount)
      if (this.walletPayAvailable) await this.createInvoice()
    },
    async createInvoice() {
      if (this.creatingInvoice) return
      if (!Number.isInteger(Number(this.amount)) || Number(this.amount) < 1) {
        Quasar.Notify.create({
          color: 'grey-10',
          textColor: 'white',
          message: this.$t('zapgoals.enter_amount'),
          icon: 'warning'
        })
        return
      }
      this.creatingInvoice = true
      let bitcoinConnect = null
      if (this.walletPayAvailable) {
        try {
          bitcoinConnect =
            await import('https://esm.sh/@getalby/bitcoin-connect@3.12.3')
          bitcoinConnect.init({
            appName: 'ZapGoals',
            showBalance: false,
            persistConnection: true
          })
        } catch (error) {
          console.error('Bitcoin Connect failed to load', error)
          Quasar.Notify.create({
            type: 'negative',
            message: this.$t('zapgoals.wallet_load_error'),
            icon: null
          })
          this.creatingInvoice = false
          return
        }
      }
      try {
        const {data} = await LNbits.api.request(
          'POST',
          `/zapgoals/api/v1/goals/${this.goalId}/invoice`,
          null,
          {
            amount: Number(this.amount),
            comment: this.comment.trim() || null
          }
        )
        this.invoice = data
        this.amountDialog = false
        this.watchInvoice(data.payment_hash)
        if (bitcoinConnect) {
          try {
            bitcoinConnect.launchPaymentModal({
              invoice: data.payment_request,
              paymentMethods: 'internal',
              onPaid: () => this.paymentComplete(),
              onCancelled: () => this.bitcoinConnectCancelled()
            })
          } catch (error) {
            console.error('Bitcoin Connect failed to open', error)
            this.closeInvoice()
            this.amountDialog = true
            Quasar.Notify.create({
              type: 'negative',
              message: this.$t('zapgoals.wallet_load_error'),
              icon: null
            })
          }
        } else {
          this.invoiceDialog = true
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.creatingInvoice = false
      }
    },
    watchInvoice(paymentHash) {
      window.clearTimeout(this.invoiceReconnectTimer)
      if (this.invoiceSocket) this.invoiceSocket.close()
      if (!paymentHash || this.destroyed) return
      const socket = new WebSocket(
        this.websocketUrl(`/api/v1/ws/${paymentHash}`)
      )
      this.invoiceSocket = socket
      socket.onopen = () => {
        this.invoiceReconnectAttempt = 0
      }
      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data)
          if (message.pending === false && message.status === 'success') {
            this.paymentComplete()
          }
        } catch (_) {}
      }
      socket.onerror = () => socket.close()
      socket.onclose = () => {
        if (this.invoiceSocket !== socket) return
        this.invoiceSocket = null
        if (this.destroyed || !this.invoice) return
        const delay = Math.min(10000, 1500 * 2 ** this.invoiceReconnectAttempt)
        this.invoiceReconnectAttempt = Math.min(
          this.invoiceReconnectAttempt + 1,
          3
        )
        this.invoiceReconnectTimer = window.setTimeout(
          () => this.watchInvoice(paymentHash),
          delay
        )
      }
    },
    bitcoinConnectCancelled() {
      if (!this.invoice) return
      this.closeInvoice()
      this.amountDialog = true
    },
    paymentComplete() {
      if (!this.invoice && !this.invoiceDialog) return
      this.invoiceDialog = false
      window.clearTimeout(this.invoiceReconnectTimer)
      if (this.invoiceSocket) this.invoiceSocket.close()
      this.invoiceSocket = null
      this.invoice = null
      this.amount = null
      this.comment = ''
      Quasar.Notify.create({
        type: 'positive',
        message: this.$t('zapgoals.thank_you'),
        icon: null
      })
      this.getGoal(true)
    },
    closeInvoice() {
      window.clearTimeout(this.invoiceReconnectTimer)
      if (this.invoiceSocket) this.invoiceSocket.close()
      this.invoiceSocket = null
      this.invoice = null
    },
    contrastColor(value) {
      const hex = String(value || '').replace('#', '')
      if (!/^[0-9a-f]{6}$/i.test(hex)) return '#111827'
      const channels = [0, 2, 4].map(index =>
        parseInt(hex.slice(index, index + 2), 16)
      )
      const luminance =
        (channels[0] * 299 + channels[1] * 587 + channels[2] * 114) / 1000
      return luminance >= 145 ? '#111827' : '#ffffff'
    },
    formatSats(value) {
      return Number(value || 0).toLocaleString()
    },
    copy(value) {
      this.utils.copyText(value)
    }
  }
}
