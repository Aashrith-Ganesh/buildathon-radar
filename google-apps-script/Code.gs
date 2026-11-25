/**
 * ==============================================================================
 * BUILDATHON RADAR - SERVERLESS WEEKLY MAILING SYSTEM
 * ==============================================================================
 * Google Apps Script (GAS) Web App & Standalone Delivery Engine
 * 
 * Architecture:
 *   GitHub Actions (Scheduled Sunday 02:30 UTC / 08:00 AM IST)
 *       ↓ HTTPS POST (with Webhook Secret & Delivery ID)
 *   Google Apps Script Web App (doPost)
 *       ↓ Authentication & Idempotency / Duplicate Check
 *   HTML & Plain-Text Email Newsletter Generator
 *       ↓ GmailApp.sendEmail
 *   Recipient Inbox
 * 
 * Script Properties:
 *   - WEBHOOK_SECRET: Secret key matching GAS_WEBHOOK_SECRET in GitHub Secrets
 *   - RECIPIENT_EMAIL: Destination inbox (defaults to Google account user)
 *   - SENDER_NAME: Friendly sender name (defaults to "Buildathon Radar")
 *   - DUPLICATE_PREVENTION_ENABLED: "true" / "false"
 * ==============================================================================
 */

// Global Defaults & Settings
var DEFAULT_CONFIG = {
  TIMEZONE: 'Asia/Kolkata',
  DEFAULT_SENDER_NAME: 'Buildathon Radar',
  MIN_DAYS_BETWEEN_DIGESTS: 5
};

// ==============================================================================
// 1. WEB APP ENTRY POINTS (doPost & doGet)
// ==============================================================================

/**
 * HTTP POST Webhook Endpoint for GitHub Actions.
 * Receives the verified digest JSON payload, authenticates the request,
 * validates required fields, verifies delivery idempotency, renders the
 * email, and dispatches via GmailApp.
 * 
 * @param {Object} e - Event parameter from Apps Script containing postData
 * @return {TextOutput} JSON response output
 */
function doPost(e) {
  var startTime = new Date().getTime();
  var props = PropertiesService.getScriptProperties();

  try {
    // 1. Validate incoming postData
    if (!e || !e.postData || !e.postData.contents) {
      return createJsonResponse({
        status: 'error',
        error: 'Malformed request: Missing postData body contents'
      }, 400);
    }

    var payload;
    try {
      payload = JSON.parse(e.postData.contents);
    } catch (parseErr) {
      return createJsonResponse({
        status: 'error',
        error: 'Invalid JSON payload: ' + parseErr.message
      }, 400);
    }

    // 2. Authenticate Webhook Secret
    var configuredSecret = props.getProperty('WEBHOOK_SECRET') || '';
    if (configuredSecret) {
      var providedSecret = '';
      if (payload.auth && payload.auth.secret) {
        providedSecret = payload.auth.secret;
      }

      if (!providedSecret || !secureCompare(providedSecret, configuredSecret)) {
        console.warn('Webhook authentication failed: Invalid or missing secret.');
        return createJsonResponse({
          status: 'error',
          error: 'Unauthorized: Invalid or missing webhook secret'
        }, 401);
      }
    } else {
      console.warn('WARNING: No WEBHOOK_SECRET set in Script Properties. Request allowed without auth check.');
    }

    // 3. Validate Payload Completeness
    validateIncomingDigest(payload);

    var deliveryId = payload.delivery_id || ('manual-' + new Date().getTime());
    var contentHash = payload.content_hash || computeDigestHash(payload);
    var isForceSend = Boolean(payload.force_send);

    // 4. Duplicate Prevention & Idempotency Check
    var dupEnabled = (props.getProperty('DUPLICATE_PREVENTION_ENABLED') || 'true').toLowerCase() === 'true';
    if (dupEnabled && !isForceSend) {
      var lastDeliveryId = props.getProperty('LAST_DELIVERY_ID');
      var lastContentHash = props.getProperty('LAST_CONTENT_HASH');
      var lastDeliveryTime = props.getProperty('LAST_DELIVERY_TIME');

      if (lastDeliveryId && lastDeliveryId === deliveryId) {
        console.log('Skipping delivery: delivery_id already processed (' + deliveryId + ').');
        return createJsonResponse({
          status: 'skipped',
          reason: 'duplicate_delivery_id',
          delivery_id: deliveryId,
          last_delivered_at: lastDeliveryTime
        }, 200);
      }

      if (lastContentHash && lastContentHash === contentHash) {
        console.log('Skipping delivery: Identical content hash already delivered (' + contentHash.substring(0, 10) + '...).');
        return createJsonResponse({
          status: 'skipped',
          reason: 'duplicate_content_hash',
          delivery_id: deliveryId,
          content_hash: contentHash,
          last_delivered_at: lastDeliveryTime
        }, 200);
      }
    }

    // 5. Determine Recipient and Sender
    var recipientEmail = payload.recipient_email || props.getProperty('RECIPIENT_EMAIL') || Session.getActiveUser().getEmail();
    var senderName = props.getProperty('SENDER_NAME') || DEFAULT_CONFIG.DEFAULT_SENDER_NAME;

    if (!recipientEmail) {
      throw new Error('No recipient email specified in payload or Script Properties.');
    }

    // 6. Render Email Formats
    var meta = payload.meta || {};
    var featured = payload.featured_hackathons || [];
    var subject = '🛰️ Buildathon Radar | ' + (meta.date_display || 'Weekly Digest') + ' | ' + featured.length + ' Featured Events';

    var htmlBody = renderDigestHtml(payload);
    var textBody = renderDigestPlainText(payload);

    // 7. Dispatch Email via GmailApp (with MailApp fallback)
    sendEmailViaGmail(recipientEmail, subject, htmlBody, textBody, senderName);

    // 8. Record Delivery State in Script Properties
    var nowIso = new Date().toISOString();
    props.setProperty('LAST_DELIVERY_ID', deliveryId);
    props.setProperty('LAST_CONTENT_HASH', contentHash);
    props.setProperty('LAST_DELIVERY_TIME', nowIso);
    props.setProperty('LAST_RECIPIENT', recipientEmail);
    props.setProperty('LAST_STATUS', 'success');

    var duration = ((new Date().getTime() - startTime) / 1000).toFixed(2);
    console.log('Successfully dispatched digest email (delivery_id=' + deliveryId + ') in ' + duration + 's to ' + recipientEmail);

    return createJsonResponse({
      status: 'success',
      delivery_id: deliveryId,
      dispatched: true,
      recipient: recipientEmail,
      featured_count: featured.length,
      duration_seconds: duration,
      timestamp: nowIso
    }, 200);

  } catch (err) {
    console.error('FATAL error in doPost: ' + err.message);
    if (props) {
      props.setProperty('LAST_ERROR', err.message);
      props.setProperty('LAST_ERROR_TIME', new Date().toISOString());
    }
    return createJsonResponse({
      status: 'error',
      error: err.message
    }, 500);
  }
}

/**
 * Health check endpoint for testing deployment reachability.
 */
function doGet(e) {
  var props = PropertiesService.getScriptProperties();
  return createJsonResponse({
    status: 'ok',
    service: 'Buildathon Radar GAS Webhook',
    version: '2.0.0',
    auth_configured: Boolean(props.getProperty('WEBHOOK_SECRET')),
    recipient_configured: Boolean(props.getProperty('RECIPIENT_EMAIL')),
    last_delivery_id: props.getProperty('LAST_DELIVERY_ID') || null,
    last_delivery_time: props.getProperty('LAST_DELIVERY_TIME') || null,
    timestamp: new Date().toISOString()
  }, 200);
}

/**
 * Helper to construct JSON response with ContentService.
 */
function createJsonResponse(dataObj, statusCode) {
  var output = ContentService.createTextOutput(JSON.stringify(dataObj));
  output.setMimeType(ContentService.MimeType.JSON);
  return output;
}

/**
 * Validates payload schema completeness.
 */
function validateIncomingDigest(data) {
  if (!data || typeof data !== 'object') {
    throw new Error('Payload must be a JSON object');
  }
  if (data.status !== 'ok') {
    throw new Error('Payload "status" must be "ok" (received: ' + data.status + ')');
  }
  if (!data.meta || typeof data.meta !== 'object') {
    throw new Error('Payload missing required "meta" object');
  }
  if (!Array.isArray(data.featured_hackathons)) {
    throw new Error('Payload missing "featured_hackathons" array');
  }
}

/**
 * Constant-time string comparison to prevent timing attacks on webhook secrets.
 */
function secureCompare(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') {
    return false;
  }
  if (a.length !== b.length) {
    return false;
  }
  var result = 0;
  for (var i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

// ==============================================================================
// 2. DUPLICATE PREVENTION & CONTENT HASHING
// ==============================================================================

/**
 * Computes a deterministic SHA-256 fingerprint for the current digest.
 */
function computeDigestHash(data) {
  var keyComponents = [];
  if (data.meta && data.meta.date_display) {
    keyComponents.push(data.meta.date_display);
  }

  var featured = data.featured_hackathons || [];
  for (var i = 0; i < featured.length; i++) {
    var f = featured[i];
    keyComponents.push((f.event_id || '') + ':' + (f.title || ''));
  }

  var textToHash = keyComponents.join('|');
  var rawHash;
  if (typeof Utilities.Charset !== 'undefined' && Utilities.Charset.UTF_8) {
    rawHash = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, textToHash, Utilities.Charset.UTF_8);
  } else {
    rawHash = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, textToHash);
  }
  var hexString = '';
  for (var j = 0; j < rawHash.length; j++) {
    var byteVal = (rawHash[j] < 0 ? rawHash[j] + 256 : rawHash[j]).toString(16);
    hexString += (byteVal.length === 1 ? '0' : '') + byteVal;
  }
  return hexString;
}

// ==============================================================================
// 3. HTML EMAIL TEMPLATE RENDERING
// ==============================================================================

/**
 * Safely escapes HTML special characters.
 */
function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Formats a raw number or string as prize pool display.
 */
function formatPrize(prize) {
  if (!prize || prize === '0' || String(prize).toLowerCase().indexOf('not listed') !== -1) {
    return null;
  }
  return escapeHtml(String(prize));
}

/**
 * Builds the responsive dark-navy / neutral themed HTML newsletter.
 * Mobile friendly, inline styles, compatible with Gmail, Apple Mail, Outlook.
 */
function renderDigestHtml(data) {
  var meta = data.meta || {};
  var profile = meta.recipient_profile || {};
  var stats = meta.summary_stats || {};
  var featured = data.featured_hackathons || [];
  var newlyDiscovered = data.newly_discovered || [];
  var deadlines = data.upcoming_deadlines || [];
  var happeningSoon = data.events_happening_soon || [];
  var recommended = data.recommended_opportunities || [];
  var changes = data.important_changes || { items: [] };
  var blackout = data.blackout_calendar || {};
  var trackedEvents = data.tracked_events || [];
  var appliedEvents = data.applied_events || [];

  var dateDisplay = escapeHtml(meta.date_display || new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }));
  var dateRange = escapeHtml(meta.date_range || '');
  var introText = escapeHtml(meta.intro || 'Here is your curated weekly hackathon radar tailored for student builders in Bengaluru.');

  // Color tokens
  var cNavBg = '#0f172a';       // Slate 900 (Dark Navy Header)
  var cPageBg = '#f8fafc';      // Slate 50 (Clean Background)
  var cCardBg = '#ffffff';      // Pure White
  var cBorder = '#e2e8f0';      // Slate 200
  var cTextPrimary = '#0f172a'; // Slate 900
  var cTextMuted = '#64748b';   // Slate 500
  var cTeal = '#0d9488';        // Teal 600
  var cTealDark = '#115e59';    // Teal 800
  var cTealLight = '#f0fdfa';   // Teal 50
  var cAmber = '#d97706';       // Amber 600
  var cAmberLight = '#fffbeb';  // Amber 50
  var cRed = '#dc2626';         // Red 600
  var fontStack = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

  // 1. Featured Hackathons HTML Cards
  var featuredCardsHtml = '';
  if (featured.length === 0) {
    featuredCardsHtml = 
      '<tr><td style="padding:20px; background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px; text-align:center; color:' + cTextMuted + '; font-style:italic;">' +
      'Quiet week: No hackathons cleared the high-relevance bar for this edition. Check upcoming deadlines and recommended opportunities below.' +
      '</td></tr>';
  } else {
    for (var i = 0; i < featured.length; i++) {
      var ev = featured[i];
      var title = escapeHtml(ev.title || 'Untitled Hackathon');
      var host = escapeHtml(ev.host || ev.source || 'Community');
      var location = escapeHtml(ev.location || 'Location Unspecified');
      var mode = (ev.mode || 'in-person').toUpperCase();
      var dates = escapeHtml(ev.dates_display || 'Dates TBD');
      var deadline = escapeHtml(ev.registration_deadline_display || 'Rolling');
      var eligibility = escapeHtml(ev.eligibility_label || ev.eligibility || 'Check Details');
      var teamSize = escapeHtml(ev.team_size || 'Solo or Teams');
      var prize = formatPrize(ev.prize);
      var summary = escapeHtml(ev.summary || '');
      var why = escapeHtml(ev.why || '');
      var url = ev.url ? escapeHtml(ev.url) : '#';
      var score = ev.score || 0;
      var trackUrl = ev.track_url ? escapeHtml(ev.track_url) : '#';
      var appliedUrl = ev.applied_url ? escapeHtml(ev.applied_url) : '#';

      var modeBadgeBg = (mode === 'IN-PERSON') ? '#ecfdf5' : '#eff6ff';
      var modeBadgeColor = (mode === 'IN-PERSON') ? '#047857' : '#1d4ed8';

      var daysBadge = '';
      if (typeof ev.days_until_deadline === 'number') {
        if (ev.days_until_deadline >= 0) {
          daysBadge = ' &middot; <span style="color:' + (ev.days_until_deadline <= 3 ? cRed : cAmber) + '; font-weight:600;">⏰ ' + ev.days_until_deadline + 'd left</span>';
        }
      }

      var prizeRow = '';
      if (prize) {
        prizeRow = 
          '<tr>' +
          '  <td style="padding:4px 0 0 0; font-size:13px; color:' + cTextPrimary + ';">' +
          '    <strong style="color:' + cTealDark + ';">🏆 Prize Pool:</strong> ' + prize +
          '  </td>' +
          '</tr>';
      }

      featuredCardsHtml += 
        '<tr>' +
        '  <td style="padding:0 0 18px 0;">' +
        '    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:10px; overflow:hidden;">' +
        '      <tr><td height="4" style="background-color:' + cTeal + '; line-height:4px; font-size:4px;">&nbsp;</td></tr>' +
        '      <tr>' +
        '        <td style="padding:18px 20px;">' +
        '          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">' +
        '            <tr>' +
        '              <td>' +
        '                <span style="display:inline-block; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:700; background-color:' + modeBadgeBg + '; color:' + modeBadgeColor + '; text-transform:uppercase; margin-right:6px;">' + mode + '</span>' +
        '                <span style="display:inline-block; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:700; background-color:' + cTealLight + '; color:' + cTealDark + '; margin-right:6px;">⭐ Score ' + score + '</span>' +
        (ev.is_bengaluru ? '<span style="display:inline-block; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:700; background-color:#fef3c7; color:#92400e; margin-right:6px;">📍 Bengaluru Local</span>' : '') +
        (ev.is_free_weekend ? '<span style="display:inline-block; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:700; background-color:#e0f2fe; color:#0369a1;">🎉 Free & Weekend</span>' : '') +
        '              </td>' +
        '            </tr>' +
        '          </table>' +
        '          <div style="margin-top:10px; font-size:18px; font-weight:700; line-height:1.3;">' +
        '            <a href="' + url + '" target="_blank" style="color:' + cNavBg + '; text-decoration:none;">' + title + '</a>' +
        '          </div>' +
        '          <div style="margin-top:4px; font-size:13px; color:' + cTextMuted + ';">' +
        '            <strong>' + host + '</strong> &middot; 📍 ' + location +
        '          </div>' +
        '          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px; font-size:13px; border-collapse:collapse;">' +
        '            <tr>' +
        '              <td style="padding:3px 0; color:' + cTextPrimary + ';"><strong style="color:#334155;">📅 Event Dates:</strong> ' + dates + '</td>' +
        '            </tr>' +
        '            <tr>' +
        '              <td style="padding:3px 0; color:' + cTextPrimary + ';"><strong style="color:#334155;">⏳ Deadline:</strong> ' + deadline + daysBadge + '</td>' +
        '            </tr>' +
        '            <tr>' +
        '              <td style="padding:3px 0; color:' + cTextPrimary + ';"><strong style="color:#334155;">🎓 Eligibility:</strong> ' + eligibility + ' &middot; <strong>👥 Team:</strong> ' + teamSize + '</td>' +
        '            </tr>' +
        prizeRow +
        '          </table>' +
        (summary ? '<div style="margin-top:12px; font-size:13px; line-height:1.5; color:#334155;">' + summary + '</div>' : '') +
        (why ? 
          '<div style="margin-top:12px; padding:10px 14px; background-color:#f8fafc; border-left:3px solid ' + cTeal + '; border-radius:4px; font-size:12px; color:#1e293b; line-height:1.4;">' +
          '  <strong>🎯 Why it matches your preferences:</strong> ' + why +
          '</div>' : '') +
        '          <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;">' +
        '            <tr>' +
        '              <td style="background-color:' + cTeal + '; border-radius:6px;">' +
        '                <a href="' + url + '" target="_blank" style="display:inline-block; padding:8px 16px; font-family:' + fontStack + '; font-size:13px; font-weight:700; color:#ffffff; text-decoration:none;">🚀 Official Link &rarr;</a>' +
        '              </td>' +
        '              <td width="10"></td>' +
        '              <td style="background-color:#f1f5f9; border-radius:6px; border:1px solid ' + cBorder + ';">' +
        '                <a href="' + trackUrl + '" target="_blank" style="display:inline-block; padding:7px 14px; font-family:' + fontStack + '; font-size:12px; font-weight:600; color:' + cTextPrimary + '; text-decoration:none;">📌 Track</a>' +
        '              </td>' +
        '              <td width="10"></td>' +
        '              <td style="background-color:' + cTealLight + '; border-radius:6px; border:1px solid ' + cTeal + ';">' +
        '                <a href="' + appliedUrl + '" target="_blank" style="display:inline-block; padding:7px 14px; font-family:' + fontStack + '; font-size:12px; font-weight:600; color:' + cTealDark + '; text-decoration:none;">🎯 Applied</a>' +
        '              </td>' +
        '            </tr>' +
        '          </table>' +
        '        </td>' +
        '      </tr>' +
        '    </table>' +
        '  </td>' +
        '</tr>';
    }
  }

  // 2. Newly Discovered Section
  var newlyDiscoveredHtml = '';
  if (newlyDiscovered.length > 0) {
    var itemsList = '';
    for (var n = 0; n < newlyDiscovered.length; n++) {
      var nItem = newlyDiscovered[n];
      itemsList += 
        '<tr style="border-bottom:1px solid ' + cBorder + ';">' +
        '  <td style="padding:10px 14px; font-size:13px;">' +
        '    <a href="' + escapeHtml(nItem.url) + '" target="_blank" style="color:' + cNavBg + '; font-weight:600; text-decoration:none;">' + escapeHtml(nItem.title) + '</a>' +
        '    <div style="font-size:12px; color:' + cTextMuted + '; margin-top:2px;">' + escapeHtml(nItem.location) + ' &middot; ' + (nItem.mode || '').toUpperCase() + '</div>' +
        '  </td>' +
        '  <td style="padding:10px 14px; font-size:12px; color:' + cTealDark + '; font-weight:700; text-align:right; white-space:nowrap;">Score ' + (nItem.score || 0) + '</td>' +
        '</tr>';
    }
    newlyDiscoveredHtml = 
      '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">🆕 Newly Discovered Opportunities</td></tr>' +
      '<tr><td>' +
      '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px; overflow:hidden;">' +
      itemsList +
      '  </table>' +
      '</td></tr>';
  }

  // 3. Upcoming Deadlines Section
  var deadlinesHtml = '';
  if (deadlines.length > 0) {
    var dRows = '';
    for (var d = 0; d < deadlines.length; d++) {
      var dItem = deadlines[d];
      var daysStr = (typeof dItem.days_until_deadline === 'number') ? (dItem.days_until_deadline + ' days left') : 'Upcoming';
      var isUrgent = (typeof dItem.days_until_deadline === 'number' && dItem.days_until_deadline <= 3);
      dRows += 
        '<tr style="border-bottom:1px solid ' + cBorder + ';">' +
        '  <td style="padding:10px 14px; font-size:13px;">' +
        '    <a href="' + escapeHtml(dItem.url) + '" target="_blank" style="color:' + cNavBg + '; font-weight:600; text-decoration:none;">' + escapeHtml(dItem.title) + '</a>' +
        '  </td>' +
        '  <td style="padding:10px 14px; font-size:12px; color:' + cTextPrimary + '; white-space:nowrap;">' + escapeHtml(dItem.registration_deadline_display) + '</td>' +
        '  <td style="padding:10px 14px; font-size:12px; font-weight:700; text-align:right; white-space:nowrap; color:' + (isUrgent ? cRed : cAmber) + ';">' + daysStr + '</td>' +
        '</tr>';
    }
    deadlinesHtml = 
      '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">⏰ Upcoming Registration Deadlines</td></tr>' +
      '<tr><td>' +
      '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px; overflow:hidden;">' +
      '    <tr style="background-color:#f1f5f9; font-size:11px; text-transform:uppercase; color:' + cTextMuted + '; font-weight:700;">' +
      '      <th align="left" style="padding:8px 14px;">Event</th>' +
      '      <th align="left" style="padding:8px 14px;">Deadline</th>' +
      '      <th align="right" style="padding:8px 14px;">Remaining</th>' +
      '    </tr>' +
      dRows +
      '  </table>' +
      '</td></tr>';
  }

  // 4. Events Happening Soon
  var happeningSoonHtml = '';
  if (happeningSoon.length > 0) {
    var soonRows = '';
    for (var s = 0; s < happeningSoon.length; s++) {
      var sItem = happeningSoon[s];
      soonRows += 
        '<tr style="border-bottom:1px solid ' + cBorder + ';">' +
        '  <td style="padding:10px 14px; font-size:13px;">' +
        '    <a href="' + escapeHtml(sItem.url) + '" target="_blank" style="color:' + cNavBg + '; font-weight:600; text-decoration:none;">' + escapeHtml(sItem.title) + '</a>' +
        '    <div style="font-size:12px; color:' + cTextMuted + ';">📍 ' + escapeHtml(sItem.location) + '</div>' +
        '  </td>' +
        '  <td style="padding:10px 14px; font-size:12px; color:' + cTealDark + '; font-weight:600; text-align:right; white-space:nowrap;">' + escapeHtml(sItem.dates_display) + '</td>' +
        '</tr>';
    }
    happeningSoonHtml = 
      '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">🚀 Events Happening Soon (Next 21 Days)</td></tr>' +
      '<tr><td>' +
      '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px; overflow:hidden;">' +
      soonRows +
      '  </table>' +
      '</td></tr>';
  }

  // 5. Recommended Opportunities (Bengaluru + Verified)
  var recommendedHtml = '';
  if (recommended.length > 0) {
    var recRows = '';
    for (var r = 0; r < recommended.length; r++) {
      var rItem = recommended[r];
      recRows += 
        '<tr style="border-bottom:1px solid ' + cBorder + ';">' +
        '  <td style="padding:10px 14px; font-size:13px;">' +
        '    <a href="' + escapeHtml(rItem.url) + '" target="_blank" style="color:' + cNavBg + '; font-weight:600; text-decoration:none;">' + escapeHtml(rItem.title) + '</a>' +
        '    <div style="font-size:12px; color:' + cTextMuted + ';">' + escapeHtml(rItem.why) + '</div>' +
        '  </td>' +
        '  <td style="padding:10px 14px; font-size:12px; text-align:right; white-space:nowrap;"><span style="color:' + cTealDark + '; font-weight:700;">Score ' + (rItem.score || 0) + '</span></td>' +
        '</tr>';
    }
    recommendedHtml = 
      '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">🎯 Recommended Opportunities (Bengaluru & Student Picks)</td></tr>' +
      '<tr><td>' +
      '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px; overflow:hidden;">' +
      recRows +
      '  </table>' +
      '</td></tr>';
  }

  // 6. Blackout Calendar Notice
  var blackoutPeriods = blackout.upcoming_periods || [];
  var blackoutList = '';
  for (var b = 0; b < blackoutPeriods.length; b++) {
    var bp = blackoutPeriods[b];
    blackoutList += '<li style="margin-bottom:4px;"><strong>' + escapeHtml(bp.dates_display) + ':</strong> ' + escapeHtml(bp.title) + (bp.reason ? ' (' + escapeHtml(bp.reason) + ')' : '') + '</li>';
  }
  var blackoutHtml = 
    '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">🛡️ Active Exam & Test Blackout Calendar</td></tr>' +
    '<tr><td>' +
    '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cAmberLight + '; border:1px solid #fcd34d; border-radius:8px; padding:14px;">' +
    '    <tr><td>' +
    '      <div style="font-size:13px; color:#78350f; font-weight:600;">' +
    '        Protected availability active: ' + (blackout.conflicts_excluded_count || 0) + ' conflicting events safely filtered out to protect your preparation schedule.' +
    '      </div>' +
    (blackoutList ? '<ul style="margin:8px 0 0 18px; padding:0; font-size:12px; color:#92400e;">' + blackoutList + '</ul>' : '') +
    '    </td></tr>' +
    '  </table>' +
    '</td></tr>';

  // 7. Tracked & Applied Events (Standing Reminders)
  var trackedHtml = '';
  if (trackedEvents.length > 0 || appliedEvents.length > 0) {
    var tRows = '';
    for (var t = 0; t < trackedEvents.length; t++) {
      var te = trackedEvents[t];
      tRows += '<tr><td style="padding:6px 12px; font-size:13px;"><a href="' + escapeHtml(te.url) + '" style="color:' + cNavBg + '; text-decoration:none;">📌 ' + escapeHtml(te.title) + '</a></td><td align="right" style="padding:6px 12px; font-size:12px; color:' + cTextMuted + ';">' + escapeHtml(te.start_display) + '</td></tr>';
    }
    for (var a = 0; a < appliedEvents.length; a++) {
      var ae = appliedEvents[a];
      tRows += '<tr><td style="padding:6px 12px; font-size:13px;"><a href="' + escapeHtml(ae.url) + '" style="color:' + cTealDark + '; font-weight:600; text-decoration:none;">🎯 ' + escapeHtml(ae.title) + '</a></td><td align="right" style="padding:6px 12px; font-size:12px; color:' + cTextMuted + ';">' + escapeHtml(ae.start_display) + '</td></tr>';
    }
    trackedHtml = 
      '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">📌 Standing Reminders (Tracked & Applied)</td></tr>' +
      '<tr><td>' +
      '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px;">' +
      tRows +
      '  </table>' +
      '</td></tr>';
  }

  // 8. Important Changes Section
  var changesHtml = '';
  if (changes.items && changes.items.length > 0) {
    var cList = '';
    for (var k = 0; k < changes.items.length; k++) {
      cList += '<li style="margin-bottom:4px;">' + escapeHtml(changes.items[k]) + '</li>';
    }
    changesHtml = 
      '<tr><td style="padding:22px 0 10px 0; font-size:16px; font-weight:700; color:' + cNavBg + ';">📊 Important Changes This Week</td></tr>' +
      '<tr><td>' +
      '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cCardBg + '; border:1px solid ' + cBorder + '; border-radius:8px; padding:14px;">' +
      '    <tr><td>' +
      '      <div style="font-size:13px; font-weight:600; color:' + cTextPrimary + ';">' + escapeHtml(changes.headline || '') + '</div>' +
      '      <ul style="margin:8px 0 0 18px; padding:0; font-size:12px; color:' + cTextMuted + ';">' + cList + '</ul>' +
      '    </td></tr>' +
      '  </table>' +
      '</td></tr>';
  }

  // Assemble full HTML document
  return '<!DOCTYPE html>' +
    '<html>' +
    '<head>' +
    '  <meta charset="utf-8">' +
    '  <meta name="viewport" content="width=device-width, initial-scale=1.0">' +
    '  <title>Buildathon Radar Weekly Digest</title>' +
    '</head>' +
    '<body style="margin:0; padding:0; background-color:' + cPageBg + '; font-family:' + fontStack + '; -webkit-font-smoothing:antialiased;">' +
    '  <div style="display:none; max-height:0px; overflow:hidden; mso-hide:all;">' +
    '    Weekly curated hackathons for Indian Class 11/12 students in Bengaluru. ' + (featured.length) + ' featured opportunities this week.' +
    '  </div>' +
    '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:' + cPageBg + ';">' +
    '    <tr>' +
    '      <td align="center" style="padding:24px 12px;">' +
    '        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px; width:100%;">' +
    '          <tr>' +
    '            <td style="background-color:' + cNavBg + '; border-radius:10px 10px 0 0; padding:28px 24px; text-align:left;">' +
    '              <div style="font-size:11px; font-weight:700; color:' + cTeal + '; letter-spacing:1px; text-transform:uppercase;">' +
    '                🛰️ BUILDATHON RADAR &middot; STUDENT EDITION' +
    '              </div>' +
    '              <div style="font-size:24px; font-weight:800; color:#ffffff; margin-top:4px; letter-spacing:-0.5px;">' +
    '                Weekly Opportunity Digest' +
    '              </div>' +
    '              <div style="font-size:13px; color:#94a3b8; margin-top:4px;">' +
    '                ' + dateDisplay + (dateRange ? ' &middot; ' + dateRange : '') + ' &middot; Bengaluru, India' +
    '              </div>' +
    '            </td>' +
    '          </tr>' +
    '          <tr>' +
    '            <td style="background-color:' + cCardBg + '; border-left:1px solid ' + cBorder + '; border-right:1px solid ' + cBorder + '; padding:18px 24px;">' +
    '              <div style="font-size:14px; line-height:1.5; color:#334155;">' +
    '                ' + introText +
    '              </div>' +
    '            </td>' +
    '          </tr>' +
    '          <tr>' +
    '            <td style="background-color:#f1f5f9; border-left:1px solid ' + cBorder + '; border-right:1px solid ' + cBorder + '; border-top:1px solid ' + cBorder + '; border-bottom:1px solid ' + cBorder + '; padding:12px 24px;">' +
    '              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">' +
    '                <tr>' +
    '                  <td align="center" style="font-size:12px; color:' + cTextMuted + ';"><strong>' + (stats.featured_count || featured.length) + '</strong> Featured</td>' +
    '                  <td align="center" style="font-size:12px; color:' + cTextMuted + ';"><strong>' + (stats.upcoming_deadlines_count || deadlines.length) + '</strong> Deadlines</td>' +
    '                  <td align="center" style="font-size:12px; color:' + cTextMuted + ';"><strong>' + (stats.blackout_conflicts_excluded || 0) + '</strong> Exam-Safe</td>' +
    '                </tr>' +
    '              </table>' +
    '            </td>' +
    '          </tr>' +
    '          <tr>' +
    '            <td style="background-color:' + cPageBg + '; border-left:1px solid ' + cBorder + '; border-right:1px solid ' + cBorder + '; padding:20px 24px;">' +
    '              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">' +
    '                <tr><td style="padding:4px 0 14px 0; font-size:18px; font-weight:800; color:' + cNavBg + ';">🔥 Featured Hackathons</td></tr>' +
    featuredCardsHtml +
    newlyDiscoveredHtml +
    deadlinesHtml +
    happeningSoonHtml +
    recommendedHtml +
    blackoutHtml +
    trackedHtml +
    changesHtml +
    '              </table>' +
    '            </td>' +
    '          </tr>' +
    '          <tr>' +
    '            <td style="background-color:' + cNavBg + '; border-radius:0 0 10px 10px; padding:24px; text-align:center; color:#94a3b8; font-size:12px; line-height:1.5;">' +
    '              <div style="font-weight:700; color:#e2e8f0; margin-bottom:4px;">Buildathon Radar Mailing System</div>' +
    '              <div>Automated weekly intelligence for high school student builders in Bengaluru.</div>' +
    '              <div style="margin-top:8px; color:#64748b;">Schedule: Sundays at 9:00 AM IST &middot; Timezone: Asia/Kolkata</div>' +
    '              <div style="margin-top:12px; font-size:11px; color:#475569;">' +
    '                You received this because you are configured as the digest recipient.' +
    '              </div>' +
    '            </td>' +
    '          </tr>' +
    '        </table>' +
    '      </td>' +
    '    </tr>' +
    '  </table>' +
    '</body>' +
    '</html>';
}

/**
 * Builds a clean plain-text alternative.
 */
function renderDigestPlainText(data) {
  var meta = data.meta || {};
  var featured = data.featured_hackathons || [];
  var deadlines = data.upcoming_deadlines || [];
  var blackout = data.blackout_calendar || {};

  var lines = [];
  lines.push('🛰️ BUILDATHON RADAR - WEEKLY DIGEST');
  lines.push('Edition: Student Edition (Class 11/12 · Bengaluru)');
  lines.push('Date: ' + (meta.date_display || '') + ' (' + (meta.date_range || '') + ')');
  lines.push('------------------------------------------------------------');
  lines.push(meta.intro || '');
  lines.push('');
  lines.push('============================================================');
  lines.push('🔥 FEATURED HACKATHONS');
  lines.push('============================================================');

  if (featured.length === 0) {
    lines.push('No events cleared the high-relevance bar this week.');
  } else {
    for (var i = 0; i < featured.length; i++) {
      var f = featured[i];
      lines.push((i + 1) + '. ' + f.title + ' [Score: ' + f.score + '/100]');
      lines.push('   Host: ' + f.host + ' | Mode: ' + (f.mode || '').toUpperCase() + ' | Location: ' + f.location);
      lines.push('   Dates: ' + f.dates_display + ' | Deadline: ' + f.registration_deadline_display);
      lines.push('   Eligibility: ' + f.eligibility_label + ' | Team: ' + f.team_size);
      if (f.prize) lines.push('   Prize: ' + f.prize);
      lines.push('   Why: ' + f.why);
      lines.push('   Link: ' + f.url);
      lines.push('');
    }
  }

  if (deadlines.length > 0) {
    lines.push('============================================================');
    lines.push('⏰ UPCOMING REGISTRATION DEADLINES');
    lines.push('============================================================');
    for (var d = 0; d < deadlines.length; d++) {
      var dl = deadlines[d];
      var days = (typeof dl.days_until_deadline === 'number') ? (' (' + dl.days_until_deadline + ' days left)') : '';
      lines.push(' - ' + dl.title + ' -> ' + dl.registration_deadline_display + days);
    }
    lines.push('');
  }

  if (blackout.upcoming_periods && blackout.upcoming_periods.length > 0) {
    lines.push('============================================================');
    lines.push('🛡️ ACTIVE EXAM & TEST BLACKOUT DATES');
    lines.push('============================================================');
    for (var b = 0; b < blackout.upcoming_periods.length; b++) {
      var bp = blackout.upcoming_periods[b];
      lines.push(' - ' + bp.dates_display + ': ' + bp.title);
    }
    lines.push('');
  }

  lines.push('------------------------------------------------------------');
  lines.push('Buildathon Radar - Automated Weekly Sunday Digest via GitHub Actions');
  return lines.join('\n');
}

// ==============================================================================
// 4. EMAIL DISPATCH & DELIVERY
// ==============================================================================

/**
 * Sends an email using GmailApp with fallback to MailApp.
 */
function sendEmailViaGmail(recipient, subject, htmlBody, textBody, senderName) {
  if (!recipient) {
    throw new Error('Recipient email is missing. Configure RECIPIENT_EMAIL in Script Properties.');
  }

  var options = {
    htmlBody: htmlBody,
    name: senderName || DEFAULT_CONFIG.DEFAULT_SENDER_NAME
  };

  try {
    GmailApp.sendEmail(recipient, subject, textBody, options);
    console.log('Successfully dispatched digest email via GmailApp to: ' + recipient);
  } catch (gmailErr) {
    console.warn('GmailApp.sendEmail failed (' + gmailErr.message + '), attempting MailApp fallback...');
    MailApp.sendEmail(recipient, subject, textBody, options);
    console.log('Successfully dispatched digest email via MailApp to: ' + recipient);
  }
}

// ==============================================================================
// 5. MANUAL TEST & CONFIGURATION UTILITIES
// ==============================================================================

/**
 * Standalone Offline Template Test:
 * Tests the HTML generator using an embedded sample payload matching sample-digest-response.json.
 */
function testWithSampleData() {
  console.log('=== TESTING HTML RENDERER WITH EMBEDDED SAMPLE PAYLOAD ===');
  var sampleData = {
    status: 'ok',
    delivery_id: 'test-sample-delivery-001',
    meta: {
      title: 'Buildathon Radar Weekly Digest',
      edition: 'Student Edition (Class 11/12 · Bengaluru)',
      date_display: 'November 29, 2026',
      date_range: 'Nov 23 - 29, 2026',
      recipient_profile: {
        name: 'Indian High School Student (Class 11/12)',
        target_city: 'Bengaluru',
        format_preference: 'In-person & Hybrid preferred',
        team_size_preference: '3-5 members',
        blackout_calendar_active: true
      },
      intro: 'Curated for Indian High School Student (Class 11/12) in Bengaluru. Strictly prioritized in-person/hybrid events and verified exam blackout date availability.',
      summary_stats: {
        total_active_events: 82,
        featured_count: 1,
        upcoming_deadlines_count: 1,
        blackout_conflicts_excluded: 27
      }
    },
    featured_hackathons: [
      {
        event_id: 'sample-blr-1',
        title: 'Bangalore GenAI Hack Night & Pitch Competition',
        host: 'Bangalore AI Innovators Group',
        source: 'Meetup Bangalore Tech',
        summary: 'Weekend in-person hackathon in Koramangala focusing on building local LLM workflows.',
        location: 'Koramangala, Bangalore',
        mode: 'in-person',
        event_start: '2026-12-05',
        event_end: '2026-12-05',
        dates_display: 'Dec 05, 2026',
        registration_deadline: '2026-12-04',
        registration_deadline_display: 'Dec 04, 2026',
        days_until_deadline: 5,
        eligibility: 'UNKNOWN',
        eligibility_label: 'High School Eligibility Unverified',
        age_restrictions: 'None specified',
        team_size: '2-4 members',
        prize: '₹75,000 + Coworking Passes',
        url: 'https://www.meetup.com/sample',
        score: 100,
        priority: 'HIGH PRIORITY',
        why: 'Free & Weekend | Core AI/ML theme | In-person in Bengaluru',
        is_bengaluru: true,
        is_free_weekend: true,
        track_url: 'http://127.0.0.1:8015/track?event_id=sample-blr-1',
        applied_url: 'http://127.0.0.1:8015/applied?event_id=sample-blr-1'
      }
    ],
    newly_discovered: [],
    upcoming_deadlines: [
      {
        title: 'Smart Bengaluru Urban Mobility Hackathon',
        registration_deadline_display: 'Nov 30, 2026',
        days_until_deadline: 1,
        url: 'https://example.com'
      }
    ],
    events_happening_soon: [],
    recommended_opportunities: [],
    important_changes: {
      headline: 'Weekly summary: 5 featured hackathons available.',
      items: ['82 active opportunities tracked across sources.']
    },
    blackout_calendar: {
      active: true,
      conflicts_excluded_count: 27,
      upcoming_periods: [
        {
          title: 'ALLEN JEE Test Period',
          dates_display: 'Nov 26 - Nov 30, 2026',
          reason: 'Internal Test Preparation'
        }
      ]
    },
    tracked_events: [],
    applied_events: []
  };

  var html = renderDigestHtml(sampleData);
  var text = renderDigestPlainText(sampleData);

  console.log('Sample Render HTML length: ' + html.length + ' chars');
  console.log('Sample Render Plain Text length: ' + text.length + ' chars');

  if (html.indexOf('Bangalore GenAI Hack Night') === -1) {
    throw new Error('Test failed: Sample title not found in HTML output.');
  }
  if (html.indexOf('Koramangala, Bangalore') === -1) {
    throw new Error('Test failed: Location not found in HTML output.');
  }
  if (html.indexOf('ALLEN JEE Test Period') === -1) {
    throw new Error('Test failed: Blackout calendar details not found in HTML output.');
  }

  console.log('=== SAMPLE DATA TEST PASSED: ALL ASSERTIONS CONFIRMED ===');
  return true;
}

/**
 * Simulates a doPost request using sample data to test webhook processing end-to-end.
 * DOES NOT send email unless forceSend is explicitly provided.
 */
function testDoPostSimulation() {
  console.log('=== SIMULATING doPost() WEBHOOK DISPATCH ===');
  var props = PropertiesService.getScriptProperties();
  var secret = props.getProperty('WEBHOOK_SECRET') || 'test-secret';

  var mockEvent = {
    postData: {
      contents: JSON.stringify({
        status: 'ok',
        delivery_id: 'test-sim-' + new Date().getTime(),
        force_send: true,
        auth: { secret: secret },
        meta: {
          title: 'Buildathon Radar Weekly Digest',
          date_display: 'Simulation Test',
          intro: 'Simulation of GitHub Actions webhook payload'
        },
        featured_hackathons: [
          {
            title: 'Simulation Hackathon',
            url: 'https://example.com',
            score: 95,
            location: 'Bengaluru',
            mode: 'in-person'
          }
        ]
      })
    }
  };

  var response = doPost(mockEvent);
  console.log('Simulation response output: ' + response.getContent());
  var parsed = JSON.parse(response.getContent());
  console.log('Response parsed status: ' + parsed.status);
  return parsed.status === 'success';
}

/**
 * Diagnostic utility to inspect current configuration without exposing the secret.
 */
function getScriptConfiguration() {
  var props = PropertiesService.getScriptProperties().getProperties();
  var secret = props.WEBHOOK_SECRET || '';
  var maskedSecret = secret ? (secret.substring(0, 3) + '...' + secret.substring(secret.length - 3)) : '(None set)';
  return {
    WEBHOOK_SECRET_CONFIGURED: Boolean(secret),
    WEBHOOK_SECRET_PREVIEW: maskedSecret,
    RECIPIENT_EMAIL: props.RECIPIENT_EMAIL || Session.getActiveUser().getEmail(),
    SENDER_NAME: props.SENDER_NAME || DEFAULT_CONFIG.DEFAULT_SENDER_NAME,
    DUPLICATE_PREVENTION_ENABLED: props.DUPLICATE_PREVENTION_ENABLED || 'true',
    LAST_DELIVERY_ID: props.LAST_DELIVERY_ID || '(None)',
    LAST_DELIVERY_TIME: props.LAST_DELIVERY_TIME || '(None)'
  };
}

/**
 * Helper to programmatically configure Script Properties from the Apps Script editor.
 */
function configureScriptProperties() {
  var properties = {
    WEBHOOK_SECRET: 'change_me_to_a_random_secure_secret', // Matches GAS_WEBHOOK_SECRET in GitHub Secrets
    RECIPIENT_EMAIL: Session.getActiveUser().getEmail(),   // Defaults to your Google account email
    SENDER_NAME: 'Buildathon Radar',
    DUPLICATE_PREVENTION_ENABLED: 'true'
  };

  PropertiesService.getScriptProperties().setProperties(properties);
  console.log('Script Properties updated:');
  console.log(getScriptConfiguration());
}
