<template id="page-zapgoals">
  <div class="row q-col-gutter-md">
    <div class="col-12 col-lg-9">
      <q-card>
        <q-card-section class="row items-center">
          <div class="col">
            <div class="text-h5" v-text="$t('zapgoals.goals')"></div>
            <div
              class="text-body2 text-grey-6"
              v-text="$t('zapgoals.admin_intro')"
            ></div>
          </div>
          <q-btn
            unelevated
            color="primary"
            icon="add"
            :label="$t('zapgoals.new_goal')"
            @click="openGoalDialog()"
          ></q-btn>
        </q-card-section>

        <q-separator></q-separator>
        <q-card-section
          v-if="loadError && !loading"
          class="text-center q-pa-xl"
        >
          <q-icon name="error_outline" color="negative" size="3rem"></q-icon>
          <div class="q-my-md" v-text="loadError"></div>
          <q-btn
            outline
            color="primary"
            :label="$t('zapgoals.retry')"
            @click="getGoals"
          ></q-btn>
        </q-card-section>
        <q-card-section
          v-else-if="!loading && !goals.length"
          class="text-center q-pa-xl"
        >
          <q-icon name="flag" color="grey-5" size="3rem"></q-icon>
          <div
            class="text-h6 q-mt-md"
            v-text="$t('zapgoals.empty_title')"
          ></div>
          <div
            class="text-body2 text-grey-6"
            v-text="$t('zapgoals.empty_body')"
          ></div>
        </q-card-section>
        <q-table
          v-else
          flat
          :grid="$q.screen.lt.md"
          :rows="goals"
          :columns="columns"
          row-key="id"
          :loading="loading"
          :pagination="{rowsPerPage: 10}"
        >
          <template v-slot:body-cell-status="props">
            <q-td :props="props">
              <q-badge
                :color="
                  goalStatus(props.row) === $t('zapgoals.active')
                    ? 'positive'
                    : 'grey'
                "
                :label="goalStatus(props.row)"
              ></q-badge>
            </q-td>
          </template>
          <template v-slot:body-cell-actions="props">
            <q-td :props="props" class="q-gutter-xs">
              <q-btn
                flat
                round
                dense
                icon="content_copy"
                :aria-label="$t('zapgoals.copy_link')"
                @click="copyPublicUrl(props.row)"
                ><q-tooltip v-text="$t('zapgoals.copy_link')"></q-tooltip
              ></q-btn>
              <q-btn
                flat
                round
                dense
                icon="open_in_new"
                type="a"
                target="_blank"
                rel="noopener"
                :href="publicUrl(props.row)"
                :aria-label="$t('zapgoals.open_link')"
                ><q-tooltip v-text="$t('zapgoals.open_link')"></q-tooltip
              ></q-btn>
              <q-btn
                flat
                round
                dense
                color="secondary"
                icon="code"
                :aria-label="$t('zapgoals.embed')"
                @click="openEmbedDialog(props.row)"
                ><q-tooltip v-text="$t('zapgoals.embed')"></q-tooltip
              ></q-btn>
              <q-btn
                v-if="props.row.recurring"
                flat
                round
                dense
                color="teal"
                icon="sync"
                :aria-label="$t('zapgoals.sweep_now')"
                :loading="sweeping"
                @click="sweepGoal(props.row)"
                ><q-tooltip v-text="$t('zapgoals.sweep_now')"></q-tooltip
              ></q-btn>
              <q-btn
                v-if="props.row.recurring"
                flat
                round
                dense
                color="info"
                icon="history"
                :aria-label="$t('zapgoals.view_periods')"
                @click="openPeriodsDialog(props.row)"
                ><q-tooltip v-text="$t('zapgoals.view_periods')"></q-tooltip
              ></q-btn>
              <q-btn
                flat
                round
                dense
                color="primary"
                icon="edit"
                :aria-label="$t('zapgoals.edit')"
                @click="openGoalDialog(props.row)"
              ></q-btn>
              <q-btn
                flat
                round
                dense
                color="negative"
                icon="delete"
                :aria-label="$t('zapgoals.delete')"
                @click="deleteGoal(props.row)"
              ></q-btn>
            </q-td>
          </template>
          <template v-slot:item="props">
            <div class="q-pa-xs col-12 col-sm-6">
              <q-card flat bordered>
                <q-card-section>
                  <div class="row items-start no-wrap">
                    <div class="col">
                      <div class="text-h6" v-text="props.row.title"></div>
                      <div
                        class="text-body2"
                        v-text="
                          `${formatSats(props.row.current_amount)} / ${formatSats(props.row.goal_amount)}`
                        "
                      ></div>
                      <div
                        class="text-caption text-grey-6"
                        v-text="formatDate(props.row.target_date)"
                      ></div>
                    </div>
                    <q-badge
                      :color="
                        goalStatus(props.row) === $t('zapgoals.active')
                          ? 'positive'
                          : 'grey'
                      "
                      :label="goalStatus(props.row)"
                    ></q-badge>
                  </div>
                </q-card-section>
                <q-card-actions align="right">
                  <q-btn
                    flat
                    round
                    icon="content_copy"
                    @click="copyPublicUrl(props.row)"
                  ></q-btn>
                  <q-btn
                    flat
                    round
                    icon="open_in_new"
                    type="a"
                    target="_blank"
                    rel="noopener"
                    :href="publicUrl(props.row)"
                  ></q-btn>
                  <q-btn
                    v-if="props.row.recurring"
                    flat
                    round
                    color="teal"
                    icon="sync"
                    :loading="sweeping"
                    :aria-label="$t('zapgoals.sweep_now')"
                    @click="sweepGoal(props.row)"
                    ><q-tooltip v-text="$t('zapgoals.sweep_now')"></q-tooltip
                  ></q-btn>
                  <q-btn
                    v-if="props.row.recurring"
                    flat
                    round
                    color="info"
                    icon="history"
                    :aria-label="$t('zapgoals.view_periods')"
                    @click="openPeriodsDialog(props.row)"
                    ><q-tooltip v-text="$t('zapgoals.view_periods')"></q-tooltip
                  ></q-btn>
                  <q-btn
                    flat
                    round
                    color="primary"
                    icon="edit"
                    @click="openGoalDialog(props.row)"
                  ></q-btn>
                  <q-btn
                    flat
                    round
                    color="negative"
                    icon="delete"
                    @click="deleteGoal(props.row)"
                  ></q-btn>
                </q-card-actions>
              </q-card>
            </div>
          </template>
        </q-table>
      </q-card>
    </div>

    <div class="col-12 col-lg-3">
      <q-card>
        <q-card-section>
          <div class="text-h6" v-text="$t('zapgoals.about_title')"></div>
          <p v-text="$t('zapgoals.about_body')"></p>
          <q-list bordered separator class="rounded-borders q-mb-md">
            <q-expansion-item dense>
              <template v-slot:header>
                <q-item-section avatar class="zapgoals-about-icon">
                  <q-icon name="alternate_email"></q-icon>
                </q-item-section>
                <q-item-section>
                  <q-item-label
                    v-text="$t('zapgoals.about_lightning_title')"
                  ></q-item-label>
                </q-item-section>
              </template>
              <div
                class="q-pa-md text-body2"
                v-text="$t('zapgoals.about_lightning_body')"
              ></div>
            </q-expansion-item>
            <q-expansion-item dense>
              <template v-slot:header>
                <q-item-section avatar class="zapgoals-about-icon">
                  <q-icon name="bolt"></q-icon>
                </q-item-section>
                <q-item-section>
                  <q-item-label
                    v-text="$t('zapgoals.about_nostr_title')"
                  ></q-item-label>
                </q-item-section>
              </template>
              <div
                class="q-pa-md text-body2"
                v-text="$t('zapgoals.about_nostr_body')"
              ></div>
            </q-expansion-item>
          </q-list>
          <div class="row items-center q-mb-md">
            <span v-text="$t('zapgoals.created_by')"></span>
            <q-btn
              flat
              dense
              no-caps
              color="primary"
              type="a"
              href="https://github.com/bitkarrot"
              target="_blank"
              rel="noopener noreferrer"
              label="bitkarrot"
            ></q-btn>
          </div>
          <div class="q-gutter-y-sm">
            <q-btn
              outline
              no-caps
              class="full-width"
              color="primary"
              icon="help_outline"
              type="a"
              href="https://github.com/bitkarrot/zapgoals#lightning-address-and-nostr-setup"
              target="_blank"
              rel="noopener noreferrer"
              :label="$t('zapgoals.setup_guide')"
            ></q-btn>
            <q-btn
              flat
              no-caps
              class="full-width"
              icon="code"
              type="a"
              href="https://github.com/bitkarrot/zapgoals"
              target="_blank"
              rel="noopener noreferrer"
              :label="$t('zapgoals.github_repository')"
            ></q-btn>
          </div>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="formDialog.show" position="top">
      <q-card
        class="q-pa-md lnbits__dialog-card"
        style="max-width: 1024px; width: 100%"
      >
        <q-card-section class="row items-center q-pb-none">
          <div
            class="text-h6"
            v-text="
              formDialog.editing
                ? $t('zapgoals.edit_goal')
                : $t('zapgoals.new_goal')
            "
          ></div>
          <q-space></q-space>
          <q-btn v-close-popup flat round dense icon="close"></q-btn>
        </q-card-section>
        <q-card-section>
          <q-form ref="goalForm" class="q-gutter-md" @submit.prevent="saveGoal">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-7">
                <q-input
                  filled
                  v-model="formDialog.data.title"
                  :label="$t('zapgoals.title') + ' *'"
                  maxlength="120"
                  counter
                  :rules="[titleRule]"
                ></q-input>
              </div>
              <div class="col-12 col-sm-5">
                <q-select
                  filled
                  emit-value
                  map-options
                  v-model="formDialog.data.wallet"
                  :options="walletOptions"
                  :label="$t('zapgoals.wallet') + ' *'"
                  :disable="formDialog.editing"
                  :rules="[value => !!value || $t('zapgoals.required')]"
                ></q-select>
              </div>
            </div>
            <q-input
              filled
              type="textarea"
              autogrow
              v-model="formDialog.data.description_above"
              :label="$t('zapgoals.description_above')"
              maxlength="2000"
              counter
              :rules="[descriptionRule]"
            ></q-input>
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-6">
                <q-input
                  filled
                  type="number"
                  min="1"
                  step="1"
                  v-model.number="formDialog.data.goal_amount"
                  :label="$t('zapgoals.goal_amount') + ' *'"
                  suffix="sats"
                  :rules="[
                    value => Number(value) >= 1 || $t('zapgoals.amount_rule')
                  ]"
                ></q-input>
              </div>
              <div class="col-12 col-sm-6">
                <q-input
                  filled
                  type="datetime-local"
                  v-model="formDialog.data.target_date"
                  :label="
                    formDialog.data.recurring
                      ? $t('zapgoals.target_date_recurring') + ' *'
                      : $t('zapgoals.target_date') + ' *'
                  "
                  stack-label
                  :hint="
                    formDialog.data.recurring
                      ? $t('zapgoals.target_date_recurring_hint')
                      : ''
                  "
                  :rules="[value => !!value || $t('zapgoals.required')]"
                ></q-input>
              </div>
            </div>
            <div>
              <div
                class="text-h5 q-mb-xs"
                v-text="$t('zapgoals.suggested_amounts')"
              ></div>
              <div
                class="text-body1 text-grey-6 q-mb-md"
                v-text="$t('zapgoals.suggested_amounts_hint')"
              ></div>
              <div class="row q-col-gutter-md">
                <div
                  v-for="index in 4"
                  :key="`suggested-${index}`"
                  class="col-12 col-sm-6 col-md-3"
                >
                  <q-input
                    filled
                    type="number"
                    min="1"
                    max="2100000000"
                    step="1"
                    v-model.number="
                      formDialog.data.suggested_amounts[index - 1]
                    "
                    :label="$t('zapgoals.suggested_amount', {index})"
                    suffix="sats"
                    :rules="[suggestedAmountRule]"
                  ></q-input>
                </div>
              </div>
            </div>

            <q-separator class="q-my-lg"></q-separator>

            <section>
              <div
                class="text-h5 q-mb-xs"
                v-text="$t('zapgoals.payment_settings')"
              ></div>
              <div
                class="text-body1 text-grey-6 q-mb-md"
                v-text="$t('zapgoals.payment_settings_hint')"
              ></div>
              <q-select
                filled
                emit-value
                map-options
                v-model="formDialog.data.wallet_mode"
                :options="modeOptions"
                :label="$t('zapgoals.payment_mode')"
              ></q-select>
              <q-banner rounded class="bg-blue-1 text-dark q-mt-md">
                <q-icon name="qr_code" class="q-mr-sm"></q-icon>
                <span v-text="$t('zapgoals.vanilla_always')"></span>
              </q-banner>
              <q-input
                filled
                class="q-mt-md"
                v-model.trim="formDialog.data.nostr_pubkey"
                :label="$t('zapgoals.nostr_pubkey')"
                maxlength="64"
                :hint="$t('zapgoals.nostr_hint')"
                :rules="[nostrRule]"
              ></q-input>
              <q-input
                filled
                v-model.trim="formDialog.data.lightning_address_username"
                :label="$t('zapgoals.lightning_username')"
                maxlength="64"
                :hint="$t('zapgoals.username_hint')"
                :rules="[usernameRule]"
              ></q-input>
            </section>

            <q-separator class="q-my-lg"></q-separator>

            <section>
              <div class="row items-center q-mb-xs">
                <q-toggle
                  v-model="formDialog.data.recurring"
                  :label="$t('zapgoals.recurring')"
                />
              </div>
              <div
                class="text-body1 text-grey-6 q-mb-md"
                v-text="$t('zapgoals.recurring_hint')"
              ></div>
              <div v-if="formDialog.data.recurring">
                <q-banner rounded class="bg-grey-2 text-dark q-mb-md">
                  <div
                    class="text-subtitle2 q-mb-xs"
                    v-text="$t('zapgoals.sweep_trigger')"
                  ></div>
                  <div
                    class="text-body2 text-grey-7 q-mb-sm"
                    v-text="$t('zapgoals.sweep_trigger_hint')"
                  ></div>
                  <div class="q-gutter-y-xs">
                    <div class="row items-center">
                      <q-icon
                        :name="
                          schedulerStatus && schedulerStatus.builtin_scheduler
                            ? 'check_circle'
                            : 'cancel'
                        "
                        :color="
                          schedulerStatus && schedulerStatus.builtin_scheduler
                            ? 'positive'
                            : 'grey-6'
                        "
                        size="1.1rem"
                        class="q-mr-xs"
                      ></q-icon>
                      <span
                        class="text-body2"
                        v-text="
                          schedulerStatus && schedulerStatus.builtin_scheduler
                            ? $t('zapgoals.builtin_scheduler_active')
                            : $t('zapgoals.builtin_scheduler_inactive')
                        "
                      ></span>
                    </div>
                    <div class="row items-center">
                      <q-icon
                        :name="
                          schedulerStatus && schedulerStatus.scheduler_extension
                            ? 'check_circle'
                            : 'cancel'
                        "
                        :color="
                          schedulerStatus && schedulerStatus.scheduler_extension
                            ? 'positive'
                            : 'grey-6'
                        "
                        size="1.1rem"
                        class="q-mr-xs"
                      ></q-icon>
                      <span
                        class="text-body2"
                        v-text="
                          schedulerStatus && schedulerStatus.scheduler_extension
                            ? $t('zapgoals.scheduler_extension_active')
                            : $t('zapgoals.scheduler_extension_inactive')
                        "
                      ></span>
                    </div>
                    <div
                      v-if="
                        schedulerStatus && schedulerStatus.scheduler_extension
                      "
                      class="row items-center"
                    >
                      <q-icon
                        :name="
                          schedulerStatus.scheduler_job_exists
                            ? 'check_circle'
                            : 'cancel'
                        "
                        :color="
                          schedulerStatus.scheduler_job_exists
                            ? 'positive'
                            : 'grey-6'
                        "
                        size="1.1rem"
                        class="q-mr-xs"
                      ></q-icon>
                      <span
                        class="text-body2"
                        v-text="
                          schedulerStatus.scheduler_job_exists
                            ? $t('zapgoals.scheduler_job_exists')
                            : $t('zapgoals.scheduler_job_missing')
                        "
                      ></span>
                      <q-btn
                        v-if="!schedulerStatus.scheduler_job_exists"
                        flat
                        dense
                        no-caps
                        color="primary"
                        size="sm"
                        icon="schedule"
                        :label="$t('zapgoals.setup_scheduler')"
                        :loading="settingUpScheduler"
                        @click="setupSchedulerJob"
                        class="q-ml-sm"
                      ></q-btn>
                    </div>
                  </div>
                </q-banner>
                <div class="row q-col-gutter-md">
                  <div class="col-12 col-sm-6">
                    <q-select
                      filled
                      emit-value
                      map-options
                      v-model="formDialog.data.recurrence_unit"
                      :options="recurrenceUnitOptions"
                      :label="$t('zapgoals.recurrence_unit') + ' *'"
                    ></q-select>
                  </div>
                  <div class="col-12 col-sm-6">
                    <q-input
                      filled
                      type="number"
                      min="1"
                      max="365"
                      step="1"
                      v-model.number="formDialog.data.recurrence_interval"
                      :label="$t('zapgoals.recurrence_interval') + ' *'"
                    ></q-input>
                  </div>
                </div>
                <div
                  v-if="formDialog.data.recurrence_unit === 'month'"
                  class="row q-col-gutter-md q-mt-md"
                >
                  <div class="col-12 col-sm-6">
                    <q-input
                      filled
                      type="number"
                      min="1"
                      max="31"
                      step="1"
                      v-model.number="formDialog.data.recurrence_day_of_month"
                      :label="$t('zapgoals.recurrence_day_of_month')"
                      :hint="$t('zapgoals.recurrence_day_hint')"
                    ></q-input>
                  </div>
                </div>
                <q-select
                  filled
                  emit-value
                  map-options
                  class="q-mt-md"
                  v-model="formDialog.data.target_wallet_id"
                  :options="walletOptions"
                  :label="$t('zapgoals.target_wallet') + ' *'"
                  :hint="$t('zapgoals.target_wallet_hint')"
                  :rules="[
                    value => !!value || $t('zapgoals.recurring_required')
                  ]"
                ></q-select>
                <q-select
                  filled
                  emit-value
                  map-options
                  class="q-mt-md"
                  v-model="formDialog.data.rollover_mode"
                  :options="rolloverModeOptions"
                  :label="$t('zapgoals.rollover_mode')"
                ></q-select>
                <q-select
                  filled
                  emit-value
                  map-options
                  class="q-mt-md"
                  v-model="formDialog.data.sweep_mode"
                  :options="sweepModeOptions"
                  :label="$t('zapgoals.sweep_mode')"
                ></q-select>
              </div>
            </section>

            <q-input
              filled
              type="textarea"
              autogrow
              v-model="formDialog.data.description_below"
              :label="$t('zapgoals.description_below')"
              maxlength="2000"
              counter
              :rules="[descriptionRule]"
            ></q-input>

            <q-separator class="q-my-lg"></q-separator>

            <section>
              <div class="text-h5 q-mb-xs" v-text="$t('zapgoals.design')"></div>
              <div
                class="text-body1 text-grey-6 q-mb-md"
                v-text="$t('zapgoals.design_hint')"
              ></div>
              <div class="row q-col-gutter-md">
                <div class="col-6 col-sm-3">
                  <q-input
                    filled
                    type="color"
                    v-model="formDialog.data.background_color"
                    :label="$t('zapgoals.background')"
                    stack-label
                  ></q-input>
                </div>
                <div class="col-6 col-sm-3">
                  <q-input
                    filled
                    type="color"
                    v-model="formDialog.data.text_color"
                    :label="$t('zapgoals.text')"
                    stack-label
                  ></q-input>
                </div>
                <div class="col-6 col-sm-3">
                  <q-input
                    filled
                    type="color"
                    v-model="formDialog.data.progress_color"
                    :label="$t('zapgoals.progress_color')"
                    stack-label
                  ></q-input>
                </div>
                <div class="col-6 col-sm-3">
                  <q-input
                    filled
                    type="color"
                    v-model="formDialog.data.remainder_color"
                    :label="$t('zapgoals.remainder_color')"
                    stack-label
                  ></q-input>
                </div>
              </div>
              <div class="row q-col-gutter-md q-mt-md">
                <div class="col-12 col-sm-8">
                  <q-select
                    filled
                    emit-value
                    map-options
                    v-model="formDialog.data.font_name"
                    :options="fontOptions"
                    :label="$t('zapgoals.font')"
                  ></q-select>
                </div>
                <div class="col-12 col-sm-4">
                  <q-select
                    filled
                    emit-value
                    map-options
                    v-model="formDialog.data.font_weight"
                    :options="fontWeightOptions"
                    :label="$t('zapgoals.font_weight')"
                  ></q-select>
                </div>
              </div>
            </section>

            <div
              class="text-h6 q-mt-md q-mb-sm"
              v-text="$t('zapgoals.live_preview')"
            ></div>
            <div
              :style="previewStyle"
              class="zapgoals-preview q-pa-md rounded-borders"
            >
              <div
                class="text-subtitle1 q-mb-sm"
                :style="{fontWeight: previewStyle.fontWeight}"
                v-text="formDialog.data.title || $t('zapgoals.preview_title')"
              ></div>
              <div
                class="zapgoals-preview-track"
                :style="previewTrackStyle"
                role="progressbar"
                :aria-valuenow="previewPercent"
                aria-valuemin="0"
                aria-valuemax="100"
              >
                <div
                  class="zapgoals-preview-fill"
                  :style="previewFillStyle"
                ></div>
                <span v-text="`${previewPercent.toFixed(1)}%`"></span>
              </div>
            </div>

            <div class="row justify-end q-gutter-sm">
              <q-btn
                flat
                :label="$t('cancel')"
                @click="closeGoalDialog"
              ></q-btn>
              <q-btn
                unelevated
                color="primary"
                type="submit"
                :loading="saving"
                :label="$t('zapgoals.save')"
              ></q-btn>
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <q-dialog v-model="periodsDialog.show">
      <q-card class="lnbits__dialog-card" style="max-width: 900px; width: 100%">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6" v-text="$t('zapgoals.view_periods')"></div>
          <q-space></q-space>
          <q-btn v-close-popup flat round dense icon="close"></q-btn>
        </q-card-section>
        <q-card-section>
          <div v-if="periodsDialog.loading" class="text-center q-pa-lg">
            <q-spinner color="primary" size="2rem"></q-spinner>
          </div>
          <q-table
            v-else-if="periodsDialog.periods.length"
            flat
            :rows="periodsDialog.periods"
            :columns="periodColumns()"
            row-key="id"
            :pagination="{rowsPerPage: 10}"
          ></q-table>
          <div v-else class="text-center q-pa-lg text-grey-6">
            <q-icon name="history" size="2rem"></q-icon>
            <div class="q-mt-sm" v-text="$t('zapgoals.no_periods')"></div>
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

    <q-dialog v-model="embedDialog.show">
      <q-card class="lnbits__dialog-card" style="max-width: 600px; width: 100%">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6" v-text="$t('zapgoals.embed')"></div>
          <q-space></q-space>
          <q-btn v-close-popup flat round dense icon="close"></q-btn>
        </q-card-section>
        <q-card-section>
          <div
            class="text-body2 text-grey-7 q-mb-md"
            v-text="$t('zapgoals.embed_hint')"
          ></div>
          <q-btn-toggle
            v-model="embedDialog.type"
            spread
            no-caps
            class="q-mb-md"
            :options="[
              {label: $t('zapgoals.embed_widget'), value: 'widget'},
              {label: $t('zapgoals.embed_iframe'), value: 'iframe'}
            ]"
          ></q-btn-toggle>
          <div
            class="text-caption text-grey-6 q-mb-md"
            v-text="
              embedDialog.type === 'widget'
                ? $t('zapgoals.embed_widget_hint')
                : $t('zapgoals.embed_iframe_hint')
            "
          ></div>
          <q-input
            filled
            readonly
            type="textarea"
            rows="6"
            :model-value="embedDialog.snippet"
            class="q-mb-md"
          >
            <template v-slot:append>
              <q-btn
                flat
                round
                dense
                icon="content_copy"
                :aria-label="$t('zapgoals.copy_snippet')"
                @click="copyEmbedSnippet"
              ></q-btn>
            </template>
          </q-input>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<style>
.zapgoals-about-icon {
  flex: 0 0 56px;
  min-width: 56px;
  align-items: center;
}
.zapgoals-preview-track {
  position: relative;
  height: 2.25rem;
  overflow: hidden;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.zapgoals-preview-fill {
  position: absolute;
  inset: 0 auto 0 0;
  transition: width 0.2s ease;
}
.zapgoals-preview-track span {
  position: relative;
  z-index: 1;
  font-weight: 700;
  color: inherit;
}
</style>
