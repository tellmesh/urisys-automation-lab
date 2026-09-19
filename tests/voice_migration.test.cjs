const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
for (const approved of [false, true]) {
  for (const dry_run of [false, true]) {
    for (const planOk of [false, true]) {
      test(`voice: approved=${approved} dry_run=${dry_run} plan=${planOk}`, async () => {
        const elements = {};
        const calls = [];
        const document = {getElementById(id) {
          return elements[id] ||= {value: 'kliknij OK', textContent: '', checked: id === 'approved' ? approved : dry_run};
        }};
        const fetch = async (url, options) => {
          calls.push(JSON.parse(options.body));
          return {json: async () => ({ok: true, result: {ok: planOk, uri: 'kvm://local/task/command/click-text', payload: {text: 'OK'}}})};
        };
        vm.runInNewContext(source, {document, fetch});
        await elements.btnChatExecute.onclick();
        assert.equal(calls[0].uri, 'llm://local/text/query/plan');
        assert.deepEqual(calls[0].context, {approved, dry_run});
        assert.equal(calls.length, planOk ? 2 : 1);
        if (planOk) {
          assert.equal(calls[1].uri, 'kvm://local/task/command/click-text');
          assert.deepEqual(calls[1].payload, {text: 'OK'});
          assert.deepEqual(calls[1].context, {approved, dry_run});
        }
      });
    }
  }
}
