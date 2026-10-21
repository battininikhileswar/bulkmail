import test from 'node:test';
import assert from 'node:assert/strict';
import {
  cleanContactName,
  cleanContactFirstName,
  sanitizeMessageForSpeech,
  describeIntent,
  formatBriefingQuestion,
} from './src/voice.js';

test('cleanContactName sanitizes contact names properly', () => {
  assert.equal(cleanContactName('John Doe'), 'John Doe');
  assert.equal(cleanContactName('  Dr. Sarah O\'Connor-Smith  '), 'Dr. Sarah O\'Connor-Smith');
  assert.equal(cleanContactName('Jane!@#$%^&*()'), 'Jane');
  assert.equal(cleanContactName(''), 'someone');
  assert.equal(cleanContactName(null), 'someone');
});

test('cleanContactFirstName extracts first name cleanly', () => {
  assert.equal(cleanContactFirstName('Alice Smith'), 'Alice');
  assert.equal(cleanContactFirstName(''), 'someone');
});

test('sanitizeMessageForSpeech strips URLs, emails, long numbers, HTML, and trims to 400 chars', () => {
  const sample = `
    Hi Team,<br>
    Please visit https://example.com/invitation?id=12345 for details.
    You can reach me at john.doe@company.org or phone 18005550199.
    <b>Looking forward to it!</b>
  `;
  const sanitized = sanitizeMessageForSpeech(sample);
  assert.ok(!sanitized.includes('https://'), 'URLs must be stripped');
  assert.ok(sanitized.includes('link'), 'URLs must be replaced with "link"');
  assert.ok(!sanitized.includes('john.doe@company.org'), 'Email must be stripped');
  assert.ok(sanitized.includes('email address'), 'Email replaced with "email address"');
  assert.ok(!sanitized.includes('18005550199'), 'Long digit sequence must be stripped');
  assert.ok(sanitized.includes('number'), 'Long digit sequence replaced with "number"');
  assert.ok(!sanitized.includes('<b>') && !sanitized.includes('<br>'), 'HTML stripped');
});

test('sanitizeMessageForSpeech cuts text over 400 chars and appends "message shortened"', () => {
  const longText = 'A'.repeat(500);
  const result = sanitizeMessageForSpeech(longText);
  assert.ok(result.endsWith('message shortened'), 'Long text must append message shortened');
  assert.ok(result.length <= 430, 'Total length should be bounded around 400 + suffix');
});

test('describeIntent maps intents to clear conversational descriptions', () => {
  assert.equal(describeIntent('question'), 'They have a question');
  assert.equal(describeIntent('pricing'), 'They are asking about pricing');
  assert.equal(describeIntent('scheduling'), 'They want to schedule a time');
  assert.equal(describeIntent('objection'), 'They have an objection');
  assert.equal(describeIntent('positive_feedback'), 'They sent positive feedback');
  assert.equal(describeIntent('unsubscribe'), 'They want to unsubscribe');
  assert.equal(describeIntent('other'), 'They sent an inquiry');
  assert.equal(describeIntent(''), 'They sent a message');
});

test('formatBriefingQuestion constructs natural phrasing with batch counts', () => {
  assert.equal(
    formatBriefingQuestion(1),
    'You have 1 new reply. Shall I read them?'
  );
  assert.equal(
    formatBriefingQuestion(2),
    'You have 2 new replies. Shall I read them?'
  );
  assert.equal(
    formatBriefingQuestion(2, { unsubscribe_request: 1 }),
    'You have 2 new replies, and 1 unsubscribe request. Shall I read them?'
  );
  assert.equal(
    formatBriefingQuestion(3, { bounce: 2, auto_reply: 1 }),
    'You have 3 new replies, and 2 bounces, 1 automatic reply. Shall I read them?'
  );
});

test('batching and duplicate filtering prevents re-announcing seen replies', () => {
  const seenIds = new Set([101, 102]);
  const incoming = [
    { id: 101, category: 'reply', body_text: 'Old' },
    { id: 102, category: 'reply', body_text: 'Old 2' },
    { id: 103, category: 'reply', body_text: 'Brand new' },
    { id: 104, category: 'unsubscribe_request', body_text: 'Stop' },
  ];

  // Filter fresh
  const fresh = incoming.filter((r) => !seenIds.has(r.id));
  assert.equal(fresh.length, 2);
  assert.deepEqual(fresh.map((r) => r.id), [103, 104]);

  // Mark seen
  fresh.forEach((r) => seenIds.add(r.id));

  // Next poll with same items yields 0 fresh items
  const nextPollFresh = incoming.filter((r) => !seenIds.has(r.id));
  assert.equal(nextPollFresh.length, 0);

  // Batching separation
  const realReplies = fresh.filter((r) => r.category === 'reply');
  const otherReplies = fresh.filter((r) => r.category !== 'reply');
  assert.equal(realReplies.length, 1);
  assert.equal(otherReplies.length, 1);
});

