<template id="page-zapgoals-public">
  <div class="zapgoals-public-page row justify-center q-py-md q-py-sm-xl">
    <div class="col-12 col-sm-9 col-md-7 col-lg-5">
      <div v-if="loading" class="text-center q-pa-xl">
        <q-spinner color="primary" size="3rem"></q-spinner>
        <div class="q-mt-md" v-text="$t('zapgoals.loading_goal')"></div>
      </div>
      <q-card v-else-if="loadError" class="q-pa-lg text-center">
        <q-icon name="error_outline" color="negative" size="3rem"></q-icon>
        <div class="text-h6 q-mt-md" v-text="loadError"></div>
        <q-btn
          outline
          color="primary"
          class="q-mt-md"
          :label="$t('zapgoals.retry')"
          @click="getGoal()"
        ></q-btn>
      </q-card>

      <q-card v-else-if="goal" :style="cardStyle" class="zapgoals-public-card">
        <q-card-section class="q-pa-lg q-pa-sm-xl">
          <h1
            class="zapgoals-title text-center q-mt-none q-mb-lg"
            v-text="goal.title"
          ></h1>
          <p
            v-if="goal.description_above"
            class="zapgoals-description q-mb-lg"
            v-text="goal.description_above"
          ></p>

          <div
            class="zapgoals-progress"
            :style="trackStyle"
            role="progressbar"
            :aria-label="$t('zapgoals.progress')"
            :aria-valuenow="actualPercent"
            aria-valuemin="0"
            :aria-valuemax="Math.max(100, actualPercent)"
          >
            <div class="zapgoals-progress-fill" :style="fillStyle"></div>
            <span class="zapgoals-percent" v-text="percentLabel"></span>
          </div>
          <div class="row justify-between q-mt-sm text-weight-medium">
            <span
              v-text="
                $t('zapgoals.current_public', {
                  amount: formatSats(goal.current_amount)
                })
              "
            ></span>
            <span
              v-text="
                $t('zapgoals.goal_public', {
                  amount: formatSats(goal.goal_amount)
                })
              "
            ></span>
          </div>

          <div class="zapgoals-target text-center q-my-lg">
            <q-icon name="event" aria-hidden="true"></q-icon>
            <span class="q-ml-xs" v-text="targetLabel"></span>
            <div class="text-weight-bold q-mt-xs" v-text="countdownLabel"></div>
          </div>

          <p
            v-if="goal.description_below"
            class="zapgoals-description q-mb-lg"
            v-text="goal.description_below"
          ></p>

          <q-form class="q-gutter-md" @submit.prevent="createInvoice">
            <q-input
              outlined
              bg-color="white"
              text-color="dark"
              type="number"
              min="1"
              step="1"
              inputmode="numeric"
              v-model.number="amount"
              :label="$t('zapgoals.zap_amount')"
              suffix="sats"
              :rules="[
                value =>
                  (Number.isInteger(Number(value)) && Number(value) >= 1) ||
                  $t('zapgoals.amount_rule')
              ]"
            ></q-input>
            <q-btn
              unelevated
              no-caps
              size="lg"
              class="full-width"
              color="primary"
              icon="bolt"
              type="submit"
              :loading="creatingInvoice"
              :label="$t('zapgoals.zap')"
            ></q-btn>
          </q-form>

          <q-separator class="q-my-lg"></q-separator>
          <div v-if="lnurlUrl" class="row items-center q-gutter-sm q-mb-sm">
            <q-icon name="qr_code_2" aria-hidden="true"></q-icon>
            <span class="col" v-text="$t('zapgoals.lnurl_pay')"></span>
            <q-btn
              flat
              round
              dense
              icon="content_copy"
              :aria-label="$t('zapgoals.copy_lnurl')"
              @click="copy(lnurlUrl)"
            ></q-btn>
            <q-btn
              flat
              round
              dense
              icon="open_in_new"
              type="a"
              target="_blank"
              rel="noopener"
              :href="lnurlUrl"
              :aria-label="$t('zapgoals.open_lnurl')"
            ></q-btn>
          </div>
          <div
            v-if="goal.lightning_address"
            class="row items-center no-wrap q-mb-sm"
          >
            <q-icon name="alternate_email" aria-hidden="true"></q-icon>
            <span
              class="col q-ml-sm zapgoals-break"
              v-text="goal.lightning_address"
            ></span>
            <q-btn
              flat
              round
              dense
              icon="content_copy"
              :aria-label="$t('zapgoals.copy_lightning_address')"
              @click="copy(goal.lightning_address)"
            ></q-btn>
          </div>
          <div v-if="goal.nostr_pubkey" class="row items-start no-wrap">
            <q-icon name="electric_bolt" aria-hidden="true"></q-icon>
            <span class="q-ml-sm" v-text="$t('zapgoals.nostr_enabled')"></span>
          </div>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="invoiceDialog" position="top" @hide="closeInvoice">
      <q-card v-if="invoice" class="q-pa-lg lnbits__dialog-card">
        <div
          class="text-h6 text-center"
          v-text="$t('zapgoals.pay_invoice')"
        ></div>
        <div
          class="text-center text-grey-7 q-mb-md"
          v-text="$t('zapgoals.qr_always')"
        ></div>
        <div class="text-center q-mb-md">
          <lnbits-qrcode
            :href="'lightning:' + invoice.payment_request"
            :value="'LIGHTNING:' + invoice.payment_request.toUpperCase()"
          ></lnbits-qrcode>
        </div>
        <q-input
          outlined
          readonly
          type="textarea"
          autogrow
          :model-value="invoice.payment_request"
          :label="$t('zapgoals.bolt11')"
        >
          <template v-slot:append>
            <q-btn
              flat
              round
              dense
              icon="content_copy"
              :aria-label="$t('zapgoals.copy_invoice')"
              @click="copy(invoice.payment_request)"
            ></q-btn>
          </template>
        </q-input>
        <q-btn
          v-if="walletPayAvailable"
          unelevated
          no-caps
          color="primary"
          icon="account_balance_wallet"
          class="full-width q-mt-md"
          :loading="walletPayLoading"
          :label="$t('zapgoals.pay_with_wallet')"
          @click="payWithWallet"
        ></q-btn>
        <div class="row justify-end q-mt-md">
          <q-btn v-close-popup flat color="grey" :label="$t('close')"></q-btn>
        </div>
      </q-card>
    </q-dialog>
  </div>
</template>

<style>
.zapgoals-public-page {
  min-height: 70vh;
}
.zapgoals-public-card {
  overflow: hidden;
  border-radius: 1.25rem;
}
.zapgoals-title {
  font-size: clamp(2rem, 8vw, 3.5rem);
  line-height: 1.08;
  overflow-wrap: anywhere;
}
.zapgoals-description {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.zapgoals-progress {
  position: relative;
  height: 3rem;
  overflow: hidden;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  outline: 1px solid rgba(0, 0, 0, 0.15);
}
.zapgoals-progress-fill {
  position: absolute;
  inset: 0 auto 0 0;
  transition: width 0.35s ease;
}
.zapgoals-percent {
  position: relative;
  z-index: 1;
  padding: 0.1rem 0.45rem;
  border-radius: 0.35rem;
  background: rgba(255, 255, 255, 0.72);
  color: #111827;
  font-weight: 800;
  font-size: 1.05rem;
}
.zapgoals-target {
  opacity: 0.9;
}
.zapgoals-break {
  overflow-wrap: anywhere;
}
@media (max-width: 599px) {
  .zapgoals-public-card {
    border-radius: 0.75rem;
  }
}
</style>
