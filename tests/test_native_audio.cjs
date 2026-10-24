const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function client(record) {
    const elements = new Map();
    const uploads = [];
    const alerts = [];
    const requests = [];
    const $ = selector => {
        if (!elements.has(selector)) {
            const element = {
                value: '', active: false,
                ready() {},
                addClass() { this.active = true; return this; },
                removeClass() { this.active = false; return this; },
                text(value) { this.value = value; return this; },
                data() { return undefined; },
            };
            elements.set(selector, element);
        }
        return elements.get(selector);
    };
    const context = vm.createContext({
        window: {webkit: {messageHandlers: {jpartyAudio: {postMessage(request) {
            requests.push(request);
            return record(request);
        }}}}},
        navigator: {}, document: {cookie: 'token=player-123'}, $, Blob, FormData, atob, Uint8Array,
        console: {log() {}}, alert(message) { alerts.push(message); },
        async fetch(url, options) { uploads.push({url, ...options}); return {ok: true}; },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../jparty/buzzer/static/buzzer.js'), 'utf8'), context);
    return {context, uploads, alerts, requests, $};
}

test('native recording works without browser media APIs and uploads authenticated M4A', async () => {
    const audio = Buffer.from('native-aac-audio');
    const c = client(async () => ({audioBase64: audio.toString('base64')}));
    await c.context.recordAutoHostAudio('answer', 9000);
    assert.equal(c.requests[0].purpose, 'answer');
    assert.equal(c.requests[0].durationMs, 9000);
    assert.equal(c.uploads[0].url, '/api/player-audio');
    const form = c.uploads[0].body;
    assert.equal(form.get('token'), 'player-123');
    assert.equal(form.get('purpose'), 'answer');
    assert.match(form.get('sequence_id'), /^\d+$/);
    assert.equal(form.get('audio').name, 'auto-host-audio.m4a');
    assert.equal(form.get('audio').type, 'audio/mp4');
    assert.deepEqual(Buffer.from(await form.get('audio').arrayBuffer()), audio);
    assert.equal(c.$('#answer-record-status').value, 'Judging...');
    assert.equal(c.$('#answer-record-status').active, false);
    assert.deepEqual(c.alerts, []);
});

test('denied microphone permission gives useful inline feedback and allows retry', async () => {
    let denied = true;
    const c = client(async () => {
        if (denied) throw new Error('Allow Microphone in Settings.');
        return {audioBase64: 'YQ=='};
    });
    await c.context.recordAutoHostAudio('clue_selection');
    assert.equal(c.uploads.length, 0);
    assert.match(c.$('#recording-status').value, /Settings/);
    assert.equal(c.$('#recording-status').active, false);
    denied = false;
    await c.context.recordAutoHostAudio('clue_selection');
    assert.equal(c.uploads.length, 1);
    assert.equal(c.$('#recording-status').value, 'Finding clue...');
});

test('rapid taps cannot start overlapping native recordings or duplicate uploads', async () => {
    let finish;
    const c = client(() => new Promise(resolve => { finish = resolve; }));
    const first = c.context.recordAutoHostAudio('answer');
    await c.context.recordAutoHostAudio('answer');
    assert.equal(c.requests.length, 1);
    finish({audioBase64: 'YQ=='});
    await first;
    assert.equal(c.uploads.length, 1);
});

test('cancelled recording never sends partial audio', async () => {
    const c = client(async () => { throw new Error('Recording stopped. Keep JParty open.'); });
    await c.context.recordAutoHostAudio('daily_double_wager');
    assert.equal(c.uploads.length, 0);
    assert.match(c.$('#dd-wager-status').value, /Keep JParty open/);
});

test('web clients still use the browser capability check', async () => {
    const c = client(async () => { throw new Error('Native path should not be used'); });
    c.context.window = {};
    await c.context.recordAutoHostAudio('answer');
    assert.equal(c.requests.length, 0);
    assert.match(c.alerts[0], /Microphone recording is not available/);
});
