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
        {label: 'System UI', value: 'system-ui, sans-serif'},
        {label: 'Arial', value: 'Arial, sans-serif'},
        {label: 'Trebuchet', value: '"Trebuchet MS", sans-serif'},
        {label: 'Verdana', value: 'Verdana, sans-serif'},
        {label: 'Tahoma', value: 'Tahoma, sans-serif'},
        {label: 'Serif', value: 'serif'},
        {label: 'Georgia', value: 'Georgia, serif'},
        {label: 'Times New Roman', value: '"Times New Roman", serif'},
        {label: 'Monospace', value: 'monospace'},
        {label: 'Courier New', value: '"Courier New", monospace'}
      ],
      fontWeightOptions: [
        {label: 'Regular', value: 400},
        {label: 'Semi-bold', value: 600},
        {label: 'Bold', value: 700},
        {label: 'Extra-bold', value: 800}
      ],
      modeOptions: [
        {label: 'Vanilla invoice only', value: 'vanilla'},
        {label: 'Bitcoin Connect', value: 'all'}
      ],
      recurrenceUnitOptions: [
        {label: 'Daily', value: 'day'},
        {label: 'Weekly', value: 'week'},
        {label: 'Monthly', value: 'month'},
        {label: 'Quarterly', value: 'quarter'},
        {label: 'Semi-annual', value: 'half_year'},
        {label: 'Annual', value: 'year'}
      ],
      rolloverModeOptions: [
        {label: 'Count excess as progress', value: 'counts_as_progress'},
        {label: 'Reset to zero', value: 'reset_to_zero'}
      ],
      sweepModeOptions: [
        {label: 'Target amount', value: 'target_amount'},
        {label: 'Entire amount', value: 'entire_amount'}
      ],
      periodsDialog: {show: false, loading: false, goal: null, periods: []},
      sweeping: false,
      schedulerStatus: null,
      settingUpScheduler: false
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
        fontFamily: data.font_name || data.font_family || 'sans-serif',
        fontWeight: Number(data.font_weight) || 400
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
        font_name: 'sans-serif',
        font_weight: 400,
        nostr_pubkey: null,
        lightning_address_username: null,
        current_amount: 0,
        recurring: false,
        recurrence_unit: 'month',
        recurrence_interval: 1,
        recurrence_day_of_month: null,
        target_wallet_id: null,
        rollover_mode: 'counts_as_progress',
        sweep_mode: 'target_amount'
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
              wallet_mode:
                goal.wallet_mode === 'nwc' ? 'all' : goal.wallet_mode,
              font_name: goal.font_name || goal.font_family || 'sans-serif',
              font_weight: Number(goal.font_weight) || 400,
              recurring: goal.recurring || false,
              recurrence_unit: goal.recurrence_unit || 'month',
              recurrence_interval: goal.recurrence_interval || 1,
              recurrence_day_of_month: goal.recurrence_day_of_month || null,
              target_wallet_id: goal.target_wallet_id || null,
              rollover_mode: goal.rollover_mode || 'counts_as_progress',
              sweep_mode: goal.sweep_mode || 'target_amount'
            }
          : this.emptyGoal()
      }
      this.fetchSchedulerStatus()
    },
    closeGoalDialog() {
      this.formDialog.show = false
    },
    async fetchSchedulerStatus() {
      const wallet = this.g.user.wallets?.[0]
      if (!wallet) return
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/zapgoals/api/v1/recurring/scheduler-status',
          wallet.inkey
        )
        this.schedulerStatus = data
      } catch (error) {
        this.schedulerStatus = null
      }
    },
    async setupSchedulerJob() {
      const wallet = this.walletFor(this.formDialog.data.wallet)
      if (!wallet) return
      this.settingUpScheduler = true
      try {
        const {data} = await LNbits.api.request(
          'POST',
          '/zapgoals/api/v1/recurring/setup-scheduler',
          wallet.adminkey
        )
        if (data.success) {
          Quasar.Notify.create({
            type: 'positive',
            message: this.$t('zapgoals.setup_scheduler_success'),
            icon: null
          })
          await this.fetchSchedulerStatus()
        } else {
          Quasar.Notify.create({
            type: 'negative',
            message: this.$t('zapgoals.setup_scheduler_failed', {
              detail: data.detail
            }),
            icon: null
          })
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.settingUpScheduler = false
      }
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
        font_name: data.font_name,
        font_weight: Number(data.font_weight),
        nostr_pubkey: data.nostr_pubkey?.trim().toLowerCase() || null,
        lightning_address_username:
          data.lightning_address_username?.trim().toLowerCase() || null,
        recurring: data.recurring || false,
        recurrence_unit: data.recurring ? data.recurrence_unit : null,
        recurrence_interval: Number(data.recurrence_interval) || 1,
        recurrence_day_of_month:
          data.recurring && data.recurrence_unit === 'month'
            ? Number(data.recurrence_day_of_month) || null
            : null,
        target_wallet_id: data.recurring ? data.target_wallet_id : null,
        rollover_mode: data.rollover_mode || 'counts_as_progress',
        sweep_mode: data.sweep_mode || 'target_amount'
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
    },
    isDue(goal) {
      return (
        goal.recurring &&
        new Date(goal.target_date).getTime() <= Date.now() &&
        !goal.sweeping
      )
    },
    sweepGoal(goal) {
      LNbits.utils
        .confirmDialog(this.$t('zapgoals.sweep_confirm'))
        .onOk(async () => {
          const wallet = this.walletFor(goal.wallet)
          if (!wallet) return
          this.sweeping = true
          try {
            const {data: period} = await LNbits.api.request(
              'POST',
              `/zapgoals/api/v1/goals/${goal.id}/sweep`,
              wallet.adminkey
            )
            const index = this.goals.findIndex(g => g.id === goal.id)
            if (index !== -1) {
              const updated = {...goal, ...period}
              this.goals.splice(index, 1, updated)
            }
            Quasar.Notify.create({
              type: 'positive',
              message: this.$t('zapgoals.sweep_success'),
              icon: null
            })
          } catch (error) {
            const detail = error?.response?.data?.detail || error?.message
            Quasar.Notify.create({
              type: 'negative',
              message: this.$t('zapgoals.sweep_failed', {detail}),
              icon: null
            })
          } finally {
            this.sweeping = false
          }
        })
    },
    async openPeriodsDialog(goal) {
      this.periodsDialog = {
        show: true,
        loading: true,
        goal,
        periods: []
      }
      const wallet = this.walletFor(goal.wallet)
      if (!wallet) {
        this.periodsDialog.loading = false
        return
      }
      try {
        const {data} = await LNbits.api.request(
          'GET',
          `/zapgoals/api/v1/goals/${goal.id}/periods`,
          wallet.inkey
        )
        this.periodsDialog.periods = Array.isArray(data) ? data : []
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.periodsDialog.loading = false
      }
    },
    periodColumns() {
      return [
        {
          name: 'index',
          label: this.$t('zapgoals.period_index'),
          field: 'period_index',
          align: 'left'
        },
        {
          name: 'start',
          label: this.$t('zapgoals.period_start'),
          field: row => this.formatDate(row.period_start),
          align: 'left'
        },
        {
          name: 'end',
          label: this.$t('zapgoals.period_end'),
          field: row => this.formatDate(row.period_end),
          align: 'left'
        },
        {
          name: 'zapped',
          label: this.$t('zapgoals.period_zapped'),
          field: row => this.formatSats(row.zapped_total),
          align: 'right'
        },
        {
          name: 'moved',
          label: this.$t('zapgoals.period_moved'),
          field: row => this.formatSats(row.moved_to_target),
          align: 'right'
        },
        {
          name: 'rollover',
          label: this.$t('zapgoals.period_rollover'),
          field: row => this.formatSats(row.rollover),
          align: 'right'
        },
        {
          name: 'swept_at',
          label: this.$t('zapgoals.period_swept_at'),
          field: row => this.formatDate(row.swept_at),
          align: 'left'
        }
      ]
    }
  }
}
