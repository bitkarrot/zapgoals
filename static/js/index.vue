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
          <p class="q-mb-none" v-text="$t('zapgoals.about_body')"></p>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="formDialog.show" position="top">
      <q-card class="q-pa-md lnbits__dialog-card" style="max-width: 760px">
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
                  :label="$t('zapgoals.target_date') + ' *'"
                  stack-label
                  :rules="[value => !!value || $t('zapgoals.required')]"
                ></q-input>
              </div>
            </div>
            <div>
              <div
                class="text-subtitle2"
                v-text="$t('zapgoals.suggested_amounts')"
              ></div>
              <div
                class="text-caption text-grey-6 q-mb-sm"
                v-text="$t('zapgoals.suggested_amounts_hint')"
              ></div>
              <div class="row q-col-gutter-sm">
                <div
                  v-for="index in 4"
                  :key="`suggested-${index}`"
                  class="col-6 col-sm-3"
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
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-6">
                <q-select
                  filled
                  emit-value
                  map-options
                  v-model="formDialog.data.wallet_mode"
                  :options="modeOptions"
                  :label="$t('zapgoals.payment_mode')"
                ></q-select>
              </div>
              <div class="col-12 col-sm-6">
                <q-select
                  filled
                  emit-value
                  map-options
                  v-model="formDialog.data.font_family"
                  :options="fontOptions"
                  :label="$t('zapgoals.font')"
                ></q-select>
              </div>
            </div>
            <q-banner rounded class="bg-blue-1 text-dark">
              <q-icon name="qr_code" class="q-mr-sm"></q-icon>
              <span v-text="$t('zapgoals.vanilla_always')"></span>
            </q-banner>
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
            <q-input
              filled
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

            <div
              class="text-subtitle2"
              v-text="$t('zapgoals.live_preview')"
            ></div>
            <div
              :style="previewStyle"
              class="zapgoals-preview q-pa-md rounded-borders"
            >
              <div
                class="text-subtitle1 q-mb-sm"
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
  </div>
</template>

<style>
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
