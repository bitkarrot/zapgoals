window.PageZapGoals = {
  template: '#page-zapgoals',
  data() {
    return {
      goals: [],
      loading: false,
      loadError: '',
      saving: false,
      formDialog: {show: false, editing: false, data: {}},
      fontOptions: [
        {label: 'Sans serif', value: 'sans-serif'},
        {label: 'Serif', value: 'serif'},
        {label: 'Monospace', value: 'monospace'}
      ],
      modeOptions: [
        {label: 'Vanilla invoice only', value: 'vanilla'},
        {label: 'Bitcoin Connect', value: 'all'}
      ]
    }
  },
  computed: {
    walletOptions() {
      return (this.g.user.wallets || []).map(wallet => ({
        label: wallet.name,
        value: wallet.id
      }))
    },
    columns() {
      return [
        {
          name: 'title',
          label: this.$t('zapgoals.title'),
          field: 'title',
          align: 'left',
          sortable: true
        },
        {
          name: 'amount',
          label: this.$t('zapgoals.progress'),
          field: row =>
            `${this.formatSats(row.current_amount)} / ${this.formatSats(row.goal_amount)}`,
          align: 'left'
        },
        {
          name: 'target',
          label: this.$t('zapgoals.target_date'),
          field: row => this.formatDate(row.target_date),
          align: 'left',
          sortable: true
        },
        {
          name: 'status',
          label: this.$t('zapgoals.status'),
          field: row => this.goalStatus(row),
          align: 'left'
        },
        {name: 'actions', label: '', field: 'id', align: 'right'}
      ]
    },
    previewPercent() {
      const target = Number(this.formDialog.data.goal_amount) || 1
      const current = Number(this.formDialog.data.current_amount) || 0
      return (current / target) * 100
    },
    previewStyle() {
      const data = this.formDialog.data
      return {
        backgroundColor: data.background_color || '#ffffff',
        color: data.text_color || '#1f2937',
        fontFamily: data.font_family || 'sans-serif'
      }
    },
    previewFillStyle() {
      return {
        width: `${Math.min(100, Math.max(0, this.previewPercent))}%`,
        backgroundColor: this.formDialog.data.progress_color || '#f59e0b'
      }
    },
    previewTrackStyle() {
      return {
        backgroundColor: this.formDialog.data.remainder_color || '#e5e7eb'
      }
    }
  },
  created() {
    this.getGoals()
  },
  methods: {
    emptyGoal() {
      return {
        wallet: this.g.user.wallets?.[0]?.id || null,
        title: '',
        description_above: '',
        description_below: '',
        goal_amount: 10000,
        target_date: '',
        suggested_amounts: [21, 100, 500, 1000],
        wallet_mode: 'vanilla',
        background_color: '#ffffff',
        text_color: '#1f2937',
        progress_color: '#f59e0b',
        remainder_color: '#e5e7eb',
        font_family: 'sans-serif',
        nostr_pubkey: null,
        lightning_address_username: null,
        current_amount: 0
      }
    },
    walletFor(id) {
      return (this.g.user.wallets || []).find(wallet => wallet.id === id)
    },
    async getGoals() {
      this.loading = true
      this.loadError = ''
      const wallets = this.g.user.wallets || []
      try {
        const results = await Promise.allSettled(
          wallets.map(wallet =>
            LNbits.api.request('GET', '/zapgoals/api/v1/goals', wallet.inkey)
          )
        )
        const successful = results.filter(
          result => result.status === 'fulfilled'
        )
        if (!successful.length && wallets.length) throw results[0].reason
        const unique = new Map()
        successful.forEach(result => {
          const rows = Array.isArray(result.value.data)
            ? result.value.data
            : result.value.data?.data || []
          rows.forEach(goal => unique.set(goal.id, goal))
        })
        this.goals = [...unique.values()]
      } catch (error) {
        this.loadError = this.$t('zapgoals.load_error')
        LNbits.utils.notifyApiError(error)
      } finally {
        this.loading = false
      }
    },
    openGoalDialog(goal = null) {
      this.formDialog = {
        show: true,
        editing: Boolean(goal),
        data: goal
          ? {
              ...goal,
              target_date: this.toLocalDateTime(goal.target_date),
              suggested_amounts: [
                ...(goal.suggested_amounts || [21, 100, 500, 1000])
              ]
                .concat(Array(4).fill(null))
                .slice(0, 4),
              wallet_mode: goal.wallet_mode === 'nwc' ? 'all' : goal.wallet_mode
            }
          : this.emptyGoal()
      }
    },
    closeGoalDialog() {
      this.formDialog.show = false
    },
    async saveGoal() {
      const valid = await this.$refs.goalForm.validate()
      if (!valid) return
      const data = this.formDialog.data
      const suggestedAmounts = (data.suggested_amounts || [])
        .filter(value => value !== null && value !== '')
        .map(Number)
      if (
        !suggestedAmounts.length ||
        new Set(suggestedAmounts).size !== suggestedAmounts.length
      ) {
        Quasar.Notify.create({
          type: 'negative',
          message: this.$t('zapgoals.suggested_amounts_rule'),
          icon: null
        })
        return
      }
      const wallet = this.walletFor(data.wallet)
      if (!wallet) return
      const payload = {
        wallet: data.wallet,
        title: data.title.trim(),
        description_above: (data.description_above || '').trim(),
        description_below: (data.description_below || '').trim(),
        goal_amount: Number(data.goal_amount),
        target_date: new Date(data.target_date).toISOString(),
        suggested_amounts: suggestedAmounts,
        wallet_mode: data.wallet_mode,
        background_color: data.background_color,
        text_color: data.text_color,
        progress_color: data.progress_color,
        remainder_color: data.remainder_color,
        font_family: data.font_family,
        nostr_pubkey: data.nostr_pubkey?.trim().toLowerCase() || null,
        lightning_address_username:
          data.lightning_address_username?.trim().toLowerCase() || null
      }
      this.saving = true
      try {
        const method = this.formDialog.editing ? 'PUT' : 'POST'
        const url = this.formDialog.editing
          ? `/zapgoals/api/v1/goals/${data.id}`
          : '/zapgoals/api/v1/goals'
        const {data: saved} = await LNbits.api.request(
          method,
          url,
          wallet.adminkey,
          payload
        )
        const index = this.goals.findIndex(goal => goal.id === saved.id)
        if (index === -1) this.goals.unshift(saved)
        else this.goals.splice(index, 1, saved)
        this.closeGoalDialog()
        Quasar.Notify.create({
          type: 'positive',
          message: this.$t('zapgoals.saved'),
          icon: null
        })
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.saving = false
      }
    },
    deleteGoal(goal) {
      LNbits.utils
        .confirmDialog(this.$t('zapgoals.delete_confirm', {title: goal.title}))
        .onOk(async () => {
          const wallet = this.walletFor(goal.wallet)
          if (!wallet) return
          try {
            await LNbits.api.request(
              'DELETE',
              `/zapgoals/api/v1/goals/${goal.id}`,
              wallet.adminkey
            )
            this.goals = this.goals.filter(item => item.id !== goal.id)
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    publicUrl(goal) {
      return `${window.location.origin}/zapgoals/${goal.id}`
    },
    copyPublicUrl(goal) {
      this.utils.copyText(this.publicUrl(goal))
    },
    formatSats(value) {
      return `${Number(value || 0).toLocaleString()} sats`
    },
    formatDate(value) {
      if (!value) return '—'
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short'
      }).format(new Date(value))
    },
    toLocalDateTime(value) {
      if (!value) return ''
      const date = new Date(value)
      const offset = date.getTimezoneOffset() * 60000
      return new Date(date.getTime() - offset).toISOString().slice(0, 16)
    },
    goalStatus(goal) {
      if (Number(goal.current_amount) >= Number(goal.goal_amount)) {
        return this.$t('zapgoals.funded')
      }
      if (new Date(goal.target_date).getTime() <= Date.now()) {
        return this.$t('zapgoals.expired')
      }
      return this.$t('zapgoals.active')
    },
    suggestedAmountRule(value) {
      return (
        value === null ||
        value === '' ||
        (Number.isInteger(Number(value)) &&
          Number(value) >= 1 &&
          Number(value) <= 2100000000) ||
        this.$t('zapgoals.amount_rule')
      )
    },
    titleRule(value) {
      return (
        (!!value && value.trim().length <= 120) ||
        this.$t('zapgoals.title_rule')
      )
    },
    descriptionRule(value) {
      return (
        !value || value.length <= 2000 || this.$t('zapgoals.description_rule')
      )
    },
    nostrRule(value) {
      return (
        !value ||
        /^[0-9a-fA-F]{64}$/.test(value) ||
        this.$t('zapgoals.nostr_rule')
      )
    },
    usernameRule(value) {
      return (
        !value ||
        /^[a-z0-9._-]{1,64}$/.test(value) ||
        this.$t('zapgoals.username_rule')
      )
    }
  }
}
