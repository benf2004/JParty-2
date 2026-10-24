const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function client() {
    const elements = new Map();
    function $(selector) {
        if (!elements.has(selector)) {
            const element = {
                visible: false, value: '', disabled: false,
                toggle(value) { this.visible = value; return this; },
                text(value) { this.value = value; return this; },
                prop(key, value) { this[key] = value; return this; },
                hide() { this.visible = false; return this; },
                show() { this.visible = true; return this; },
                ready() { return this; },
            };
            elements.set(selector, element);
        }
        return elements.get(selector);
    }
    const sent = [];
    const context = vm.createContext({
        window: {}, document: {}, console: {log() {}}, $,
        location: {protocol: 'http:', host: 'localhost'},
        WebSocket: class { send(value) { sent.push(JSON.parse(value)); } },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../jparty/buzzer/static/buzzer.js'), 'utf8'), context);
    context.updater.start();
    return {
        context, $, sent,
        receive(state) {
            context.updater.socket.onmessage({data: JSON.stringify({
                message: 'START_GAME_COUNTDOWN', text: JSON.stringify(state),
            })});
        },
    };
}

test('shared countdown shows cancel for everyone and hides start until cancelled', () => {
    const c = client();
    c.receive({seconds_remaining: 3, can_start_game: true});
    assert.equal(c.$('#cancel-start-game-button').visible, true);
    assert.equal(c.$('#start-game-button').visible, false);
    assert.match(c.$('#start-countdown-status').value, /Starting in 3/);
    c.context.setAutoHostControls({can_start_game: true});
    assert.equal(c.$('#start-game-button').visible, false);
    c.receive({seconds_remaining: 2, can_start_game: true});
    assert.match(c.$('#start-countdown-status').value, /Starting in 2/);
    c.context.cancelStartGame();
    assert.equal(c.sent.at(-1).message, 'CANCEL_START_GAME');
    c.receive({seconds_remaining: 0, can_start_game: true, message: 'Start cancelled: players changed'});
    assert.equal(c.$('#cancel-start-game-button').visible, false);
    assert.equal(c.$('#start-game-button').visible, true);
    assert.equal(c.$('#start-game-button').disabled, false);
    assert.match(c.$('#start-countdown-status').value, /players changed/);
});

test('manual-host countdown offers phone cancellation and clears controls on start', () => {
    const c = client();
    c.receive({seconds_remaining: 3, can_start_game: false});
    assert.equal(c.$('#cancel-start-game-button').visible, true);
    assert.equal(c.$('#start-game-button').visible, false);
    c.receive({seconds_remaining: 0, can_start_game: false});
    assert.equal(c.$('#cancel-start-game-button').visible, false);
    assert.equal(c.$('#start-game-button').visible, false);
    assert.equal(c.$('#start-countdown-status').value, '');
});

test('service verification stays cancellable and offline services hide start', () => {
    const c = client();
    c.receive({seconds_remaining: 0, checking_services: true, can_start_game: true});
    assert.equal(c.$('#cancel-start-game-button').visible, true);
    assert.equal(c.$('#start-game-button').visible, false);
    assert.match(c.$('#start-countdown-status').value, /Checking Auto Host/);
    c.receive({seconds_remaining: 0, can_start_game: false, message: 'Auto Host needs attention'});
    assert.equal(c.$('#start-game-button').visible, false);
    assert.equal(c.$('#cancel-start-game-button').visible, false);
    assert.match(c.$('#start-countdown-status').value, /needs attention/);
});
