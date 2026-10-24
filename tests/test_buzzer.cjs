const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function buzzerClient() {
    const timers = [];
    // Stub DOM operations, keeping the real socket handler and page routing.
    const element = new Proxy({}, {get: () => () => element});
    const context = vm.createContext({
        window: {}, document: {}, console: {log() {}},
        location: {protocol: 'http:', host: 'localhost'},
        WebSocket: class {},
        $: () => element,
        setTimeout(callback, delay) { timers.push({callback, delay}); },
        clearInterval() {},
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../jparty/buzzer/static/buzzer.js'), 'utf8'), context);
    context.updater.start();
    return {
        context,
        send(message, text = '') {
            context.updater.socket.onmessage({data: JSON.stringify({message, text})});
        },
        finishResultDelay() {
            timers.filter(timer => timer.delay === 1800).forEach(timer => timer.callback());
        },
    };
}

test('dispute result timeout preserves the newly awarded clue picker', () => {
    const client = buzzerClient();
    client.context.load_page('dispute');
    client.send('DISPUTE_RESULT', 'Dispute accepted. B receives the points.');
    client.send('PROMPT_SELECT_CLUE', JSON.stringify({auto_start_delay_ms: 800}));
    client.finishResultDelay();
    assert.equal(client.context.current_page, 'select');
});

test('dispute result returns other voters to the buzzer', () => {
    const client = buzzerClient();
    client.context.load_page('dispute');
    client.send('DISPUTE_RESULT', 'Dispute accepted. B receives the points.');
    client.finishResultDelay();
    assert.equal(client.context.current_page, 'buzz');
});
