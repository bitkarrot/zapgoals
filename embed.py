"""Standalone embeddable ZapGoals card page and JS widget.

Serves a self-contained HTML page (for iframe embedding) and a JS
widget (for direct embedding via <script> tag) that render a public
goal card without the LNbits SPA shell.
"""

from fastapi.responses import HTMLResponse, PlainTextResponse

EMBED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZapGoal</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:sans-serif;background:transparent;overflow-x:hidden}
#zapgoals-card{
  max-width:500px;margin:0 auto;padding:2rem;border-radius:1.25rem;
  overflow:hidden;background:#fff;color:#1f2937;font-size:16px;
  font-weight:400;
}
.zg-title{font-size:clamp(1.5rem,6vw,2.5rem);line-height:1.1;text-align:center;
  margin-bottom:1rem;overflow-wrap:anywhere;font-weight:inherit}
.zg-desc{white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:1rem;
  font-weight:inherit}
.zg-progress{position:relative;height:3rem;overflow:hidden;border-radius:999px;
  display:flex;align-items:center;justify-content:center;
  outline:1px solid rgba(0,0,0,.15);background:#e5e7eb}
.zg-progress-fill{position:absolute;inset:0 auto 0 0;transition:width .35s ease}
.zg-percent{position:relative;z-index:1;padding:.1rem .45rem;border-radius:.35rem;
  background:rgba(255,255,255,.72);color:#111827;font-weight:800;font-size:1.05rem}
.zg-amounts{display:flex;justify-content:space-between;margin-top:.5rem;
  font-weight:inherit}
.zg-target{text-align:center;margin:1rem 0;opacity:.9;font-weight:inherit}
.zg-recurring{text-align:center;margin-bottom:1rem}
.zg-recurring-badge{display:inline-flex;align-items:center;gap:.25rem;
  background:#0d9488;color:#fff;padding:.35rem .65rem;border-radius:.4rem;
  font-size:.85rem;font-weight:600}
.zg-zap-btn{display:block;width:100%;padding:.85rem;border:none;border-radius:.75rem;
  font-size:1.05rem;font-weight:700;cursor:pointer;color:#fff;background:#f59e0b;
  transition:opacity .15s}
.zg-zap-btn:hover{opacity:.9}
.zg-zap-btn:active{opacity:.8}
.zg-separator{height:1px;background:rgba(0,0,0,.1);margin:1rem 0}
.zg-lnaddr{display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem;
  font-weight:inherit}
.zg-lnaddr span{flex:1;overflow-wrap:anywhere}
.zg-copy-btn{background:none;border:none;cursor:pointer;padding:.25rem;
  color:inherit;opacity:.6}
.zg-copy-btn:hover{opacity:1}
.zg-nostr{display:flex;align-items:flex-start;gap:.5rem;font-weight:inherit}
.zg-loading{text-align:center;padding:3rem;color:#999}
.zg-error{text-align:center;padding:3rem;color:#e00}
/* Dialog */
.zg-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;
  z-index:9999;align-items:center;justify-content:center;padding:1rem}
.zg-overlay.show{display:flex}
.zg-dialog{background:#fff;border-radius:1rem;padding:1.5rem;max-width:420px;
  width:100%;color:#111}
.zg-dialog-header{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:1rem}
.zg-dialog-title{font-size:1.25rem;font-weight:700}
.zg-close{background:none;border:none;font-size:1.5rem;cursor:pointer;
  color:#999;line-height:1}
.zg-selected{text-align:center;padding:1rem 0}
.zg-selected-value{font-size:3rem;font-weight:700;line-height:1}
.zg-sats-label{font-size:1rem;color:#666;margin-top:.25rem}
.zg-amounts-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.5rem;
  margin-bottom:1rem}
.zg-amt-btn{padding:.75rem;border:1px solid #ddd;border-radius:.6rem;
  font-size:1rem;font-weight:600;cursor:pointer;background:#fff;color:#111;
  transition:background .15s}
.zg-amt-btn.active{background:#f59e0b;color:#fff;border-color:#f59e0b}
.zg-amt-btn:hover{border-color:#f59e0b}
.zg-input{width:100%;padding:.6rem;border:1px solid #ddd;border-radius:.4rem;
  font-size:1rem;margin-bottom:.75rem}
.zg-textarea{width:100%;padding:.6rem;border:1px solid #ddd;border-radius:.4rem;
  font-size:1rem;resize:vertical;margin-bottom:.75rem;min-height:60px}
.zg-submit{display:block;width:100%;padding:.8rem;border:none;border-radius:.6rem;
  font-size:1.05rem;font-weight:700;cursor:pointer;color:#fff;background:#f59e0b}
.zg-qr{text-align:center;margin:1rem 0}
.zg-qr img{max-width:280px;width:100%;height:auto}
.zg-invoice-box{margin-top:.5rem}
.zg-invoice-text{width:100%;font-size:.8rem;font-family:monospace;padding:.5rem;
  border:1px solid #ddd;border-radius:.4rem;word-break:break-all;resize:none;
  background:#f9f9f9;color:#333}
.zg-thankyou{text-align:center;padding:2rem 1rem}
.zg-thankyou h3{font-size:1.5rem;margin-bottom:.5rem}
.zg-thankyou p{color:#666}
</style>
</head>
<body>
<div id="zapgoals-card">
  <div class="zg-loading">Loading goal…</div>
</div>
<div class="zg-overlay" id="zg-overlay">
  <div class="zg-dialog" id="zg-dialog"></div>
</div>
<script>
(function(){
  var GOAL_ID = window.location.pathname.match(/\\/zapgoals\\/([^/]+)\\/embed/);
  GOAL_ID = GOAL_ID ? GOAL_ID[1] : '';
  var ORIGIN = window.location.origin;
  var card = document.getElementById('zapgoals-card');
  var overlay = document.getElementById('zg-overlay');
  var dialog = document.getElementById('zg-dialog');
  var goal = null;
  var amount = null;
  var comment = '';
  var invoice = null;
  var goalSocket = null;
  var invoiceSocket = null;
  var countdownTimer = null;
  var now = Date.now();

  function api(method, path, body){
    var opts = {method: method, headers: {'Content-Type': 'application/json'}};
    if(body) opts.body = JSON.stringify(body);
    return fetch(ORIGIN + path, opts).then(function(r){
      if(!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function escapeHtml(s){
    var d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function formatSats(v){
    return Number(v || 0).toLocaleString() + ' sats';
  }

  function formatDate(v){
    if(!v) return '—';
    return new Intl.DateTimeFormat(undefined, {dateStyle:'long',timeStyle:'short'})
      .format(new Date(v));
  }

  function contrastColor(hex){
    hex = String(hex || '').replace('#','');
    if(!/^[0-9a-f]{6}$/i.test(hex)) return '#111827';
    var r=parseInt(hex.slice(0,2),16),g=parseInt(hex.slice(2,4),16),b=parseInt(hex.slice(4,6),16);
    var lum=(r*299+g*587+b*114)/1000;
    return lum >= 145 ? '#111827' : '#ffffff';
  }

  function renderGoal(){
    if(!goal) return;
    var fw = Number(goal.font_weight) || 400;
    var ff = goal.font_name || goal.font_family || 'sans-serif';
    card.style.background = goal.background_color || '#fff';
    card.style.color = goal.text_color || '#1f2937';
    card.style.fontFamily = ff;
    card.style.fontWeight = fw;

    var pct = 0;
    if(goal.percent !== undefined && goal.percent !== null){
      pct = Number(goal.percent) || 0;
    } else {
      var target = Number(goal.goal_amount) || 0;
      pct = target ? (Number(goal.current_amount||0)/target)*100 : 0;
    }
    var capped = Math.min(100, Math.max(0, pct));
    var pctLabel = pct >= 1000
      ? pct.toLocaleString(undefined,{maximumFractionDigits:1})+'%'
      : pct.toFixed(1)+'%';

    var diff = new Date(goal.target_date).getTime() - now;
    var countdown = '';
    if(Number(goal.current_amount) >= Number(goal.goal_amount)){
      countdown = 'Goal reached — thank you!';
    } else if(diff <= 0){
      countdown = goal.status || 'Goal ended';
    } else {
      var days=Math.floor(diff/86400000);
      var hours=Math.floor((diff%86400000)/3600000);
      var mins=Math.floor((diff%3600000)/60000);
      var secs=Math.floor((diff%60000)/1000);
      if(days) countdown = days+'d '+hours+'h remaining';
      else if(hours) countdown = hours+'h '+mins+'m remaining';
      else countdown = mins+'m '+secs+'s remaining';
    }

    var html = '';
    html += '<h1 class="zg-title" style="font-weight:'+fw+'">'+escapeHtml(goal.title)+'</h1>';
    if(goal.description_above)
      html += '<p class="zg-desc" style="font-weight:'+fw+'">'+escapeHtml(goal.description_above)+'</p>';

    html += '<div class="zg-progress" style="background:'+(goal.remainder_color||'#e5e7eb')+'">'
      + '<div class="zg-progress-fill" style="width:'+capped+'%;background:'+(goal.progress_color||'#f59e0b')+'"></div>'
      + '<span class="zg-percent">'+pctLabel+'</span></div>';

    html += '<div class="zg-amounts" style="font-weight:'+fw+'">'
      + '<span>Current '+formatSats(goal.current_amount)+'</span>'
      + '<span>Goal '+formatSats(goal.goal_amount)+'</span></div>';

    html += '<div class="zg-target" style="font-weight:'+fw+'">'
      + '📅 <span>'+formatDate(goal.target_date)+'</span>'
      + '<div style="font-weight:700;margin-top:.25rem">'+escapeHtml(countdown)+'</div></div>';

    if(goal.recurring && goal.show_period_badge !== false){
      html += '<div class="zg-recurring">'
        + '<span class="zg-recurring-badge">🔄 Period '+(goal.period_index+1)+'</span></div>';
    }

    if(goal.description_below)
      html += '<p class="zg-desc" style="font-weight:'+fw+'">'+escapeHtml(goal.description_below)+'</p>';

    var btnColor = goal.progress_color || '#f59e0b';
    var btnText = contrastColor(btnColor);
    html += '<button class="zg-zap-btn" style="background:'+btnColor+';color:'+btnText+'" onclick="window.__zgOpenAmount()">⚡ Zap this goal</button>';

    if(goal.lightning_address || goal.nostr_pubkey){
      html += '<div class="zg-separator"></div>';
    }
    if(goal.lightning_address){
      html += '<div class="zg-lnaddr" style="font-weight:'+fw+'">'
        + '✉ <span>'+escapeHtml(goal.lightning_address)+'</span>'
        + '<button class="zg-copy-btn" onclick="window.__zgCopy(\\''+goal.lightning_address+'\\')">📋</button></div>';
    }
    if(goal.nostr_pubkey){
      html += '<div class="zg-nostr" style="font-weight:'+fw+'">⚡ Nostr zaps are enabled for this goal.</div>';
    }

    card.innerHTML = html;
    sendHeight();
  }

  function sendHeight(){
    var h = document.documentElement.scrollHeight;
    window.parent.postMessage({type:'zapgoals-embed-height', height: h}, '*');
  }

  function getGoal(silent){
    if(!silent) card.innerHTML = '<div class="zg-loading">Loading goal…</div>';
    api('GET', '/zapgoals/api/v1/goals/'+GOAL_ID+'/public').then(function(data){
      goal = data;
      renderGoal();
    }).catch(function(){
      card.innerHTML = '<div class="zg-error">This goal is unavailable.</div>';
      sendHeight();
    });
  }

  function openAmountDialog(){
    amount = null;
    comment = '';
    var suggested = (goal.suggested_amounts || [21,100,500,1000]).slice(0,4);
    var btnColor = goal.progress_color || '#f59e0b';
    var btnText = contrastColor(btnColor);

    var html = '<div class="zg-dialog-header">'
      + '<div class="zg-dialog-title">Choose your zap</div>'
      + '<button class="zg-close" onclick="window.__zgCloseDialog()">×</button></div>';
    html += '<div class="zg-selected"><div class="zg-selected-value" id="zg-selected-val">—</div>'
      + '<div class="zg-sats-label">sats</div></div>';
    html += '<div class="zg-amounts-grid">';
    suggested.forEach(function(s){
      html += '<button class="zg-amt-btn" onclick="window.__zgSelectAmount('+s+')">'+formatSats(s)+'</button>';
    });
    html += '</div>';
    html += '<input class="zg-input" type="number" min="1" step="1" placeholder="Custom amount (sats)" id="zg-custom-amt" oninput="window.__zgCustomAmount(this.value)">';
    html += '<textarea class="zg-textarea" placeholder="Comment (optional)" id="zg-comment" oninput="window.__zgComment=this.value" maxlength="280"></textarea>';
    html += '<button class="zg-submit" style="background:'+btnColor+';color:'+btnText+'" onclick="window.__zgCreateInvoice()">Continue to payment</button>';

    dialog.innerHTML = html;
    overlay.classList.add('show');
    window.__zgComment = '';
  }

  function selectAmount(s){
    amount = s;
    var el = document.getElementById('zg-selected-val');
    if(el) el.textContent = Number(s).toLocaleString();
    var btns = dialog.querySelectorAll('.zg-amt-btn');
    btns.forEach(function(b){
      b.classList.toggle('active', b.textContent.indexOf(Number(s).toLocaleString()) !== -1);
    });
    if(goal.wallet_mode === 'all'){
      overlay.classList.remove('show');
      createInvoice();
    }
  }

  var creatingInvoice = false;
  function createInvoice(){
    if(creatingInvoice) return;
    if(!amount || amount < 1) return;
    creatingInvoice = true;
    overlay.classList.remove('show');

    api('POST', '/zapgoals/api/v1/goals/'+GOAL_ID+'/invoice', {
      amount: Number(amount), comment: (comment||'').trim() || null
    }).then(function(data){
      invoice = data;
      watchInvoice(data.payment_hash);

      if(goal.wallet_mode === 'all'){
        tryBitcoinConnect(data.payment_request);
      } else {
        showInvoiceDialog();
      }
    }).catch(function(e){
      creatingInvoice = false;
      alert('Could not create invoice: ' + e.message);
    });
  }

  var bcPayment = null;
  function tryBitcoinConnect(paymentRequest){
    // Bitcoin Connect uses localStorage to persist wallet connections.
    // In a cross-origin iframe, browsers may block localStorage access
    // (Safari by default, Chrome with third-party cookie blocking).
    // If init() or launchPaymentModal() throws, fall back to QR-only.
    try {
      import('https://esm.sh/@getalby/bitcoin-connect@3.12.3').then(function(bc){
        try {
          bc.init({appName:'ZapGoals', showBalance:false, persistConnection:true});
          bcPayment = bc.launchPaymentModal({
            invoice: paymentRequest,
            paymentMethods: 'all',
            onPaid: function(){ paymentComplete(); },
            onCancelled: function(){ closeDialog(); }
          });
        } catch(e) {
          console.warn('Bitcoin Connect failed in iframe, falling back to QR:', e);
          showInvoiceDialog();
        }
      }).catch(function(e){
        console.warn('Bitcoin Connect import failed, falling back to QR:', e);
        showInvoiceDialog();
      });
    } catch(e) {
      console.warn('Bitcoin Connect unavailable, falling back to QR:', e);
      showInvoiceDialog();
    }
  }

  function showInvoiceDialog(){
    var html = '<div class="zg-dialog-header">'
      + '<div class="zg-dialog-title">Pay Lightning invoice</div>'
      + '<button class="zg-close" onclick="window.__zgCloseDialog()">×</button></div>';
    html += '<div class="zg-qr"><img src="https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=LIGHTNING:'+encodeURIComponent(invoice.payment_request.toUpperCase())+'" alt="QR code"></div>';
    html += '<div class="zg-invoice-box"><textarea class="zg-invoice-text" readonly rows="3">'+escapeHtml(invoice.payment_request)+'</textarea></div>';
    html += '<div style="text-align:center;margin-top:.75rem"><button class="zg-copy-btn" onclick="window.__zgCopy(\\''+invoice.payment_request+'\\')">📋 Copy invoice</button></div>';
    if(goal.wallet_mode === 'all'){
      html += '<div style="text-align:center;margin-top:.5rem;font-size:.85rem;color:#666">'
        + 'Wallet payment unavailable in embed? '
        + '<a href="'+ORIGIN+'/zapgoals/'+GOAL_ID+'" target="_blank" rel="noopener" style="color:#f59e0b">Open full page</a></div>';
    }

    dialog.innerHTML = html;
    overlay.classList.add('show');
  }

  function watchInvoice(paymentHash){
    if(invoiceSocket) invoiceSocket.close();
    var wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/api/v1/ws/' + paymentHash;
    invoiceSocket = new WebSocket(wsUrl);
    invoiceSocket.onmessage = function(event){
      try {
        var msg = JSON.parse(event.data);
        if(msg.pending === false && msg.status === 'success') paymentComplete();
      } catch(e){}
    };
    invoiceSocket.onclose = function(){
      invoiceSocket = null;
    };
  }

  function paymentComplete(){
    if(bcPayment && bcPayment.setPaid){
      var p = bcPayment;
      bcPayment = null;
      p.setPaid({preimage: ''});
    }
    if(invoiceSocket){ invoiceSocket.close(); invoiceSocket = null; }
    invoice = null;
    creatingInvoice = false;
    overlay.classList.remove('show');
    var html = '<div class="zg-thankyou"><h3>Payment received</h3><p>Thank you!</p></div>';
    dialog.innerHTML = html;
    overlay.classList.add('show');
    setTimeout(function(){ overlay.classList.remove('show'); }, 3000);
    getGoal(true);
  }

  function closeDialog(){
    overlay.classList.remove('show');
    if(invoiceSocket){ invoiceSocket.close(); invoiceSocket = null; }
    creatingInvoice = false;
    bcPayment = null;
  }

  function copyText(text){
    navigator.clipboard.writeText(text).catch(function(){});
  }

  // WebSocket for live goal updates
  function connectGoalSocket(){
    if(goalSocket) goalSocket.close();
    var wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/api/v1/ws/' + GOAL_ID;
    goalSocket = new WebSocket(wsUrl);
    goalSocket.onmessage = function(){ getGoal(true); };
    goalSocket.onclose = function(){
      goalSocket = null;
      setTimeout(connectGoalSocket, 3000);
    };
  }

  // Countdown timer
  countdownTimer = setInterval(function(){ now = Date.now(); if(goal) renderGoal(); }, 1000);

  // Expose handlers for inline onclick
  window.__zgOpenAmount = openAmountDialog;
  window.__zgSelectAmount = selectAmount;
  window.__zgCustomAmount = function(v){ amount = Number(v) || null; var el = document.getElementById('zg-selected-val'); if(el) el.textContent = v ? Number(v).toLocaleString() : '—'; var btns = dialog.querySelectorAll('.zg-amt-btn'); btns.forEach(function(b){b.classList.remove('active')}); };
  window.__zgCreateInvoice = createInvoice;
  window.__zgCloseDialog = closeDialog;
  window.__zgCopy = copyText;

  // Init
  getGoal();
  connectGoalSocket();
  window.addEventListener('resize', sendHeight);
  window.addEventListener('load', sendHeight);
})();
</script>
</body>
</html>"""


async def embed_page(goal_id: str) -> HTMLResponse:
    """Serve a standalone embeddable goal card page (iframe)."""
    return HTMLResponse(content=EMBED_HTML, media_type="text/html")


WIDGET_JS = """
(function(){
  // Find this script tag to read data-goal and detect server origin
  var scripts = document.querySelectorAll('script[src*="/zapgoals/embed.js"]');
  var scriptTag = scripts[scripts.length - 1];
  if(!scriptTag) return;
  var goalId = scriptTag.getAttribute('data-goal');
  if(!goalId) return;
  var srcUrl = new URL(scriptTag.src);
  var ORIGIN = srcUrl.origin;

  // Create container and shadow DOM
  var container = document.createElement('div');
  container.className = 'zapgoals-widget-container';
  scriptTag.parentNode.insertBefore(container, scriptTag);
  var shadow = container.attachShadow({mode: 'open'});

  var goal = null;
  var amount = null;
  var comment = '';
  var invoice = null;
  var goalSocket = null;
  var invoiceSocket = null;
  var countdownTimer = null;
  var now = Date.now();

  function api(method, path, body){
    var opts = {method: method, headers: {'Content-Type': 'application/json'}};
    if(body) opts.body = JSON.stringify(body);
    return fetch(ORIGIN + path, opts).then(function(r){
      if(!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }
  function escapeHtml(s){var d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
  function formatSats(v){return Number(v||0).toLocaleString()+' sats';}
  function formatDate(v){if(!v)return '\\u2014';return new Intl.DateTimeFormat(undefined,{dateStyle:'long',timeStyle:'short'}).format(new Date(v));}
  function contrastColor(hex){hex=String(hex||'').replace('#','');if(!/^[0-9a-f]{6}$/i.test(hex))return '#111827';var r=parseInt(hex.slice(0,2),16),g=parseInt(hex.slice(2,4),16),b=parseInt(hex.slice(4,6),16);var lum=(r*299+g*587+b*114)/1000;return lum>=145?'#111827':'#ffffff';}

  var style = document.createElement('style');
  style.textContent = `
*{margin:0;padding:0;box-sizing:border-box}
:host{display:block}
.zg-card{max-width:500px;margin:0 auto;padding:2rem;border-radius:1.25rem;overflow:hidden;background:#fff;color:#1f2937;font-size:16px;font-weight:400;font-family:sans-serif}
.zg-title{font-size:clamp(1.5rem,6vw,2.5rem);line-height:1.1;text-align:center;margin-bottom:1rem;overflow-wrap:anywhere;font-weight:inherit}
.zg-desc{white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:1rem;font-weight:inherit}
.zg-progress{position:relative;height:3rem;overflow:hidden;border-radius:999px;display:flex;align-items:center;justify-content:center;outline:1px solid rgba(0,0,0,.15);background:#e5e7eb}
.zg-progress-fill{position:absolute;inset:0 auto 0 0;transition:width .35s ease}
.zg-percent{position:relative;z-index:1;padding:.1rem .45rem;border-radius:.35rem;background:rgba(255,255,255,.72);color:#111827;font-weight:800;font-size:1.05rem}
.zg-amounts{display:flex;justify-content:space-between;margin-top:.5rem;font-weight:inherit}
.zg-target{text-align:center;margin:1rem 0;opacity:.9;font-weight:inherit}
.zg-recurring{text-align:center;margin-bottom:1rem}
.zg-recurring-badge{display:inline-flex;align-items:center;gap:.25rem;background:#0d9488;color:#fff;padding:.35rem .65rem;border-radius:.4rem;font-size:.85rem;font-weight:600}
.zg-zap-btn{display:block;width:100%;padding:.85rem;border:none;border-radius:.75rem;font-size:1.05rem;font-weight:700;cursor:pointer;color:#fff;background:#f59e0b;transition:opacity .15s}
.zg-zap-btn:hover{opacity:.9}
.zg-separator{height:1px;background:rgba(0,0,0,.1);margin:1rem 0}
.zg-lnaddr{display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem;font-weight:inherit}
.zg-lnaddr span{flex:1;overflow-wrap:anywhere}
.zg-copy-btn{background:none;border:none;cursor:pointer;padding:.25rem;color:inherit;opacity:.6;font-size:1rem}
.zg-copy-btn:hover{opacity:1}
.zg-nostr{display:flex;align-items:flex-start;gap:.5rem;font-weight:inherit}
.zg-loading{text-align:center;padding:3rem;color:#999}
.zg-error{text-align:center;padding:3rem;color:#e00}
.zg-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;z-index:2147483647;align-items:center;justify-content:center;padding:1rem}
.zg-overlay.show{display:flex}
.zg-dialog{background:#fff;border-radius:1rem;padding:1.5rem;max-width:420px;width:100%;color:#111}
.zg-dialog-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem}
.zg-dialog-title{font-size:1.25rem;font-weight:700}
.zg-close{background:none;border:none;font-size:1.5rem;cursor:pointer;color:#999;line-height:1}
.zg-selected{text-align:center;padding:1rem 0}
.zg-selected-value{font-size:3rem;font-weight:700;line-height:1}
.zg-sats-label{font-size:1rem;color:#666;margin-top:.25rem}
.zg-amounts-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.5rem;margin-bottom:1rem}
.zg-amt-btn{padding:.75rem;border:1px solid #ddd;border-radius:.6rem;font-size:1rem;font-weight:600;cursor:pointer;background:#fff;color:#111;transition:background .15s}
.zg-amt-btn.active{background:#f59e0b;color:#fff;border-color:#f59e0b}
.zg-amt-btn:hover{border-color:#f59e0b}
.zg-input{width:100%;padding:.6rem;border:1px solid #ddd;border-radius:.4rem;font-size:1rem;margin-bottom:.75rem}
.zg-textarea{width:100%;padding:.6rem;border:1px solid #ddd;border-radius:.4rem;font-size:1rem;resize:vertical;margin-bottom:.75rem;min-height:60px}
.zg-submit{display:block;width:100%;padding:.8rem;border:none;border-radius:.6rem;font-size:1.05rem;font-weight:700;cursor:pointer;color:#fff;background:#f59e0b}
.zg-qr{text-align:center;margin:1rem 0}
.zg-qr img{max-width:280px;width:100%;height:auto}
.zg-invoice-box{margin-top:.5rem}
.zg-invoice-text{width:100%;font-size:.8rem;font-family:monospace;padding:.5rem;border:1px solid #ddd;border-radius:.4rem;word-break:break-all;resize:none;background:#f9f9f9;color:#333}
.zg-thankyou{text-align:center;padding:2rem 1rem}
.zg-thankyou h3{font-size:1.5rem;margin-bottom:.5rem}
.zg-thankyou p{color:#666}
`;
  shadow.appendChild(style);

  var card = document.createElement('div');
  card.className = 'zg-card';
  card.innerHTML = '<div class="zg-loading">Loading goal\\u2026</div>';
  shadow.appendChild(card);

  var overlay = document.createElement('div');
  overlay.className = 'zg-overlay';
  shadow.appendChild(overlay);

  function renderGoal(){
    if(!goal) return;
    var fw = Number(goal.font_weight)||400;
    var ff = goal.font_name||goal.font_family||'sans-serif';
    card.style.background = goal.background_color||'#fff';
    card.style.color = goal.text_color||'#1f2937';
    card.style.fontFamily = ff;
    card.style.fontWeight = fw;

    var pct = 0;
    if(goal.percent!==undefined&&goal.percent!==null){pct=Number(goal.percent)||0;}
    else{var target=Number(goal.goal_amount)||0;pct=target?(Number(goal.current_amount||0)/target)*100:0;}
    var capped = Math.min(100,Math.max(0,pct));
    var pctLabel = pct>=1000?pct.toLocaleString(undefined,{maximumFractionDigits:1})+'%':pct.toFixed(1)+'%';

    var diff = new Date(goal.target_date).getTime()-now;
    var countdown = '';
    if(Number(goal.current_amount)>=Number(goal.goal_amount)){countdown='Goal reached \\u2014 thank you!';}
    else if(diff<=0){countdown=goal.status||'Goal ended';}
    else{var days=Math.floor(diff/86400000),hours=Math.floor((diff%86400000)/3600000),mins=Math.floor((diff%3600000)/60000),secs=Math.floor((diff%60000)/1000);
    if(days)countdown=days+'d '+hours+'h remaining';else if(hours)countdown=hours+'h '+mins+'m remaining';else countdown=mins+'m '+secs+'s remaining';}

    var btnColor = goal.progress_color||'#f59e0b';
    var btnText = contrastColor(btnColor);

    var html = '<h1 class="zg-title" style="font-weight:'+fw+'">'+escapeHtml(goal.title)+'</h1>';
    if(goal.description_above) html += '<p class="zg-desc" style="font-weight:'+fw+'">'+escapeHtml(goal.description_above)+'</p>';
    html += '<div class="zg-progress" style="background:'+(goal.remainder_color||'#e5e7eb')+'"><div class="zg-progress-fill" style="width:'+capped+'%;background:'+(goal.progress_color||'#f59e0b')+'"></div><span class="zg-percent">'+pctLabel+'</span></div>';
    html += '<div class="zg-amounts" style="font-weight:'+fw+'"><span>Current '+formatSats(goal.current_amount)+'</span><span>Goal '+formatSats(goal.goal_amount)+'</span></div>';
    html += '<div class="zg-target" style="font-weight:'+fw+'">\\ud83d\\udcc5 <span>'+formatDate(goal.target_date)+'</span><div style="font-weight:700;margin-top:.25rem">'+escapeHtml(countdown)+'</div></div>';
    if(goal.recurring && goal.show_period_badge !== false) html += '<div class="zg-recurring"><span class="zg-recurring-badge">\\ud83d\\udd04 Period '+(goal.period_index+1)+'</span></div>';
    if(goal.description_below) html += '<p class="zg-desc" style="font-weight:'+fw+'">'+escapeHtml(goal.description_below)+'</p>';
    html += '<button class="zg-zap-btn" style="background:'+btnColor+';color:'+btnText+'">\\u26a1 Zap this goal</button>';
    if(goal.lightning_address||goal.nostr_pubkey) html += '<div class="zg-separator"></div>';
    if(goal.lightning_address) html += '<div class="zg-lnaddr" style="font-weight:'+fw+'">\\u2709 <span>'+escapeHtml(goal.lightning_address)+'</span><button class="zg-copy-btn" data-copy="'+escapeHtml(goal.lightning_address)+'">\\ud83d\\udccb</button></div>';
    if(goal.nostr_pubkey) html += '<div class="zg-nostr" style="font-weight:'+fw+'">\\u26a1 Nostr zaps are enabled for this goal.</div>';
    card.innerHTML = html;

    var zapBtn = card.querySelector('.zg-zap-btn');
    if(zapBtn) zapBtn.addEventListener('click', openAmountDialog);
    var copyBtns = card.querySelectorAll('[data-copy]');
    copyBtns.forEach(function(b){b.addEventListener('click',function(){copyText(b.getAttribute('data-copy'));});});
  }

  function getGoal(silent){
    if(!silent) card.innerHTML = '<div class="zg-loading">Loading goal\\u2026</div>';
    api('GET','/zapgoals/api/v1/goals/'+goalId+'/public').then(function(data){
      goal = data; renderGoal();
    }).catch(function(){
      card.innerHTML = '<div class="zg-error">This goal is unavailable.</div>';
    });
  }

  function openAmountDialog(){
    amount = null; comment = '';
    var suggested = (goal.suggested_amounts||[21,100,500,1000]).slice(0,4);
    var btnColor = goal.progress_color||'#f59e0b';
    var btnText = contrastColor(btnColor);

    var html = '<div class="zg-dialog-header"><div class="zg-dialog-title">Choose your zap</div><button class="zg-close">\\u00d7</button></div>';
    html += '<div class="zg-selected"><div class="zg-selected-value" id="zg-sel">\\u2014</div><div class="zg-sats-label">sats</div></div>';
    html += '<div class="zg-amounts-grid">';
    suggested.forEach(function(s){html += '<button class="zg-amt-btn" data-amt="'+s+'">'+formatSats(s)+'</button>';});
    html += '</div>';
    html += '<input class="zg-input" type="number" min="1" step="1" placeholder="Custom amount (sats)" id="zg-custom">';
    html += '<textarea class="zg-textarea" placeholder="Comment (optional)" id="zg-comment" maxlength="280"></textarea>';
    html += '<button class="zg-submit" style="background:'+btnColor+';color:'+btnText+'">Continue to payment</button>';

    var dlg = document.createElement('div');
    dlg.className = 'zg-dialog';
    dlg.innerHTML = html;
    overlay.innerHTML = '';
    overlay.appendChild(dlg);
    overlay.classList.add('show');

    dlg.querySelector('.zg-close').addEventListener('click', closeDialog);
    dlg.querySelectorAll('.zg-amt-btn').forEach(function(b){
      b.addEventListener('click', function(){selectAmount(Number(b.getAttribute('data-amt')), dlg);});
    });
    var customInput = dlg.querySelector('#zg-custom');
    customInput.addEventListener('input', function(){
      amount = Number(customInput.value) || null;
      var sel = dlg.querySelector('#zg-sel');
      if(sel) sel.textContent = customInput.value ? Number(customInput.value).toLocaleString() : '\\u2014';
      dlg.querySelectorAll('.zg-amt-btn').forEach(function(b){b.classList.remove('active');});
    });
    var commentInput = dlg.querySelector('#zg-comment');
    commentInput.addEventListener('input', function(){comment = commentInput.value;});
    dlg.querySelector('.zg-submit').addEventListener('click', createInvoice);
  }

  function selectAmount(s, dlg){
    amount = s;
    var sel = dlg.querySelector('#zg-sel');
    if(sel) sel.textContent = Number(s).toLocaleString();
    dlg.querySelectorAll('.zg-amt-btn').forEach(function(b){
      b.classList.toggle('active', Number(b.getAttribute('data-amt'))===s);
    });
    if(goal.wallet_mode==='all'){
      overlay.classList.remove('show');
      createInvoice();
    }
  }

  var creatingInvoice = false;
  var bcPayment = null;
  function createInvoice(){
    if(creatingInvoice) return;
    if(!amount||amount<1) return;
    creatingInvoice = true;
    overlay.classList.remove('show');
    api('POST','/zapgoals/api/v1/goals/'+goalId+'/invoice',{amount:Number(amount),comment:(comment||'').trim()||null}).then(function(data){
      invoice = data;
      watchInvoice(data.payment_hash);
      if(goal.wallet_mode==='all'){
        // Bitcoin Connect runs in first-party context here (host page),
        // so localStorage and popups work normally.
        import('https://esm.sh/@getalby/bitcoin-connect@3.12.3').then(function(bc){
          bc.init({appName:'ZapGoals',showBalance:false,persistConnection:true});
          bcPayment = bc.launchPaymentModal({
            invoice: data.payment_request,
            paymentMethods: 'all',
            onPaid: function(){paymentComplete();},
            onCancelled: function(){closeDialog();}
          });
        }).catch(function(e){
          console.warn('Bitcoin Connect failed, falling back to QR:', e);
          showInvoiceDialog();
        });
      } else {
        showInvoiceDialog();
      }
    }).catch(function(e){
      creatingInvoice = false;
      alert('Could not create invoice: '+e.message);
    });
  }

  function showInvoiceDialog(){
    var html = '<div class="zg-dialog-header"><div class="zg-dialog-title">Pay Lightning invoice</div><button class="zg-close">\\u00d7</button></div>';
    html += '<div class="zg-qr"><img src="https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=LIGHTNING:'+encodeURIComponent(invoice.payment_request.toUpperCase())+'" alt="QR code"></div>';
    html += '<div class="zg-invoice-box"><textarea class="zg-invoice-text" readonly rows="3">'+escapeHtml(invoice.payment_request)+'</textarea></div>';
    html += '<div style="text-align:center;margin-top:.75rem"><button class="zg-copy-btn" data-copy="'+escapeHtml(invoice.payment_request)+'">\\ud83d\\udccb Copy invoice</button></div>';

    var dlg = document.createElement('div');
    dlg.className = 'zg-dialog';
    dlg.innerHTML = html;
    overlay.innerHTML = '';
    overlay.appendChild(dlg);
    overlay.classList.add('show');

    dlg.querySelector('.zg-close').addEventListener('click', closeDialog);
    dlg.querySelector('[data-copy]').addEventListener('click', function(){
      copyText(invoice.payment_request);
    });
  }

  function watchInvoice(paymentHash){
    if(invoiceSocket) invoiceSocket.close();
    var wsUrl = (ORIGIN.indexOf('https')===0?'wss:':'ws:')+'//'+ORIGIN.replace(/^https?:\\/\\//,'')+'/api/v1/ws/'+paymentHash;
    invoiceSocket = new WebSocket(wsUrl);
    invoiceSocket.onmessage = function(event){
      try{var msg=JSON.parse(event.data);if(msg.pending===false&&msg.status==='success')paymentComplete();}catch(e){}
    };
    invoiceSocket.onclose = function(){invoiceSocket=null;};
  }

  function paymentComplete(){
    if(bcPayment && bcPayment.setPaid){
      var p = bcPayment;
      bcPayment = null;
      p.setPaid({preimage: ''});
    }
    if(invoiceSocket){invoiceSocket.close();invoiceSocket=null;}
    invoice = null;
    creatingInvoice = false;
    overlay.classList.remove('show');
    var dlg = document.createElement('div');
    dlg.className = 'zg-dialog';
    dlg.innerHTML = '<div class="zg-thankyou"><h3>Payment received</h3><p>Thank you!</p></div>';
    overlay.innerHTML = '';
    overlay.appendChild(dlg);
    overlay.classList.add('show');
    setTimeout(function(){overlay.classList.remove('show');}, 3000);
    getGoal(true);
  }

  function closeDialog(){
    overlay.classList.remove('show');
    if(invoiceSocket){invoiceSocket.close();invoiceSocket=null;}
    creatingInvoice = false;
    bcPayment = null;
  }

  function copyText(text){try{navigator.clipboard.writeText(text);}catch(e){}}

  function connectGoalSocket(){
    if(goalSocket) goalSocket.close();
    var wsUrl = (ORIGIN.indexOf('https')===0?'wss:':'ws:')+'//'+ORIGIN.replace(/^https?:\\/\\//,'')+'/api/v1/ws/'+goalId;
    goalSocket = new WebSocket(wsUrl);
    goalSocket.onmessage = function(){getGoal(true);};
    goalSocket.onclose = function(){goalSocket=null;setTimeout(connectGoalSocket,3000);};
  }

  countdownTimer = setInterval(function(){now=Date.now();if(goal)renderGoal();}, 1000);

  getGoal();
  connectGoalSocket();
})();
"""


async def embed_widget() -> PlainTextResponse:
    """Serve the JS widget for direct embedding via <script> tag."""
    return PlainTextResponse(
        content=WIDGET_JS.strip(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )
