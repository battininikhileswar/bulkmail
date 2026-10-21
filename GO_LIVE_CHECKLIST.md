# Go-Live Readiness Checklist

Complete and verify each item before disabling Test Mode and starting real email campaigns.

- [ ] **1. Consent & Compliance:** All contacts explicitly opted in or agreed to receive these communications.
- [ ] **2. Sender & Unsubscribe Line:** The email footer displays the real sender name and a working unsubscribe instruction (`Reply 'UNSUBSCRIBE'`).
- [ ] **3. Rendering & Deliverability:** Sent test emails to a personal inbox, verified on both desktop and mobile, and confirmed they do not land in Spam/Junk.
- [ ] **4. Sending Caps:** Configured daily send cap is set below the email provider's allowable limits (e.g. max 400 for standard Gmail).
- [ ] **5. Pilot Batch:** Dispatched a small pilot batch of 20 to 50 real emails first, actively monitoring for bounces, replies, and spam complaints before full dispatch.
- [ ] **6. Human-in-the-Loop AI:** Confirmed AI responses generate drafts only; every draft response is reviewed and approved by a human before dispatch.
- [ ] **7. Verified Event Facts:** `backend/facts.json` is populated with actual, accurate event details and do-not-answer topics (refunds, discounts, complaints).
- [ ] **8. Database Backup:** Clicked "Backup now" on the Settings page to create a timestamped database backup prior to the live send.
- [ ] **9. Emergency Pause Switch:** Tested the top-bar global pause button (`⏸ Pause Sending`) to confirm it immediately halts all outgoing campaign and reply sends.
