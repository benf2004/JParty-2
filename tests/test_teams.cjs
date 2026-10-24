const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function client(cookie = "") {
    let readyCallback;
    const elements = new Map();
    function element() {
        return {
            visible: false, value: '', children: [], content: '',
            toggle(value) { this.visible = value; return this; },
            text(value) { if (value === undefined) return this.content; this.content = value; return this; },
            val(value) { if (value === undefined) return this.value; this.value = value; return this; },
            empty() { this.children = []; return this; },
            append(value) { this.children.push(value); return this; },
            prop(key, value) { this[key] = value; return this; },
            hide() { this.visible = false; return this; },
            show() { this.visible = true; return this; },
            ready(callback) { readyCallback = callback; return this; },
            on() { return this; },
            attr() { return this; },
            css() { return this; },
        };
    }
    function $(selector) {
        if (selector === '<option>') return element();
        if (!elements.has(selector)) elements.set(selector, element());
        return elements.get(selector);
    }
    const sent = [];
    const context = vm.createContext({
        window: {addEventListener() {}},
        document: {cookie, querySelector() { return {style: {}, offsetWidth: 400, getContext() { return {scale() {}}; }}; }},
        SignaturePad: class {clear() {}}, console: {log() {}}, $,
        location: {protocol: 'http:', host: 'localhost'},
        WebSocket: class { send(value) { sent.push(JSON.parse(value)); } },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../jparty/buzzer/static/buzzer.js'), 'utf8'), context);
    context.updater.start();
    return {context, $, sent, boot() { readyCallback(); context.updater.socket.onopen(); }, receive(message, state) {
        context.updater.socket.onmessage({data: JSON.stringify({message, text: JSON.stringify(state)})});
    }};
}

const state = {
    team_mode: true, joined: true, in_lobby: true, team_id: 'team-1', team_name: 'Red',
    representative: 'Ada', is_representative: true, score: 1200,
    teams: [{id: 'team-1', name: 'Red', members: 2}, {id: 'team-2', name: 'Blue', members: 1}],
};

test('team updates show shared score, representative and lobby team selection', () => {
    const c = client();
    c.receive('TEAM_STATE', state);
    assert.equal(c.$('#team-banner').visible, true);
    assert.match(c.$('#team-summary').content, /Red.*1,200.*Ada.*you/);
    assert.equal(c.$('#lobby-team').value, 'team-1');
    assert.equal(c.$('#lobby-team-section').visible, true);
    assert.equal(c.$('#join-team').children.length, 3);
    c.context.changeTeam('team-2');
    assert.equal(c.sent.at(-1).message, 'CHANGE_TEAM');
    assert.equal(c.sent.at(-1).text, 'team-2');
});

test('team choices freeze on game start while team identity stays visible', () => {
    const c = client();
    c.receive('TEAM_STATE', {...state, in_lobby: false});
    assert.equal(c.$('#lobby-team-section').visible, false);
    assert.equal(c.$('#team-banner').visible, true);
    c.context.changeTeam('team-2');
    assert.equal(c.sent.length, 0);
});

test('team registration includes team id and prevents missing selection', () => {
    const c = client();
    c.receive('TEAM_STATE', {...state, joined: false, team_id: null});
    c.$('#join-team').val('');
    c.context.nameForm('signature', 'Phone Only', 'Ben');
    assert.equal(c.sent.length, 0);
    assert.match(c.$('#team-error').content, /Choose a team/);
    c.$('#join-team').val('team-2');
    c.context.nameForm('signature', 'Phone Only', 'Ben');
    assert.equal(c.sent.at(-1).team_id, 'team-2');
    assert.equal(c.sent.at(-1).displayName, 'Ben');
});

test('setup changes reach waiting phones without exposing joined-only controls', () => {
    const c = client();
    c.receive('TEAM_STATE', {...state, joined: false, team_id: null,
        teams: [{id: 'team-1', name: '<script>Team</script>', members: 0}]});
    assert.equal(c.$('#lobby-team-section').visible, false);
    assert.equal(c.$('#join-team').children[1].content, '<script>Team</script> (0)');
    assert.equal(c.$('#display-name-section').visible, true);
});

test('individual mode keeps team controls hidden and sends no team id', () => {
    const c = client();
    c.receive('TEAM_STATE', {team_mode: false, teams: [], joined: true});
    assert.equal(c.$('#team-banner').visible, false);
    assert.equal(c.$('#join-team-section').visible, false);
    c.context.nameForm('signature', 'Phone Only', 'Ben');
    assert.equal(c.sent.at(-1).team_id, null);
});


test('a first phone visit requests lobby configuration without a saved token', () => {
    const c = client();
    c.boot();
    assert.equal(c.sent.at(-1).message, 'CHECK_IF_EXISTS');
    assert.equal(c.sent.at(-1).text, '');
    assert.equal(c.context.current_page, 'name');
});

test('a returning phone requests its saved player state', () => {
    const c = client('token=existing-token');
    c.boot();
    assert.equal(c.sent.at(-1).message, 'CHECK_IF_EXISTS');
    assert.equal(c.sent.at(-1).text, 'existing-token');
});
