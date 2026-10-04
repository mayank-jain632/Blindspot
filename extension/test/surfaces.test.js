'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {visibleInputs,openTabs}=require('../surfaces');
function fixture(){
  const reads=[];
  class TabInputText{constructor(uri){this.uri=uri;}}
  const pane=(name,column)=>({viewColumn:column,document:{uri:{scheme:'file',fsPath:name},lineCount:5,isDirty:false,version:1,getText(){reads.push(name);return 'a\nb\nc\nd\ne';}},visibleRanges:[{start:{line:0,character:0},end:{line:2,character:0}}]});
  const left=pane('a.py',1),right=pane('b.py',2);
  const tab=name=>({input:new TabInputText({fsPath:name})});
  const api={TabInputText,window:{state:{focused:true},activeTextEditor:left,visibleTextEditors:[left,right],tabGroups:{all:[{viewColumn:1,activeTab:tab('a.py'),tabs:[tab('a.py'),tab('c.py')]},{viewColumn:2,activeTab:tab('b.py'),tabs:[tab('b.py')]}]}}};
  return {api,reads,left,right,relative:uri=>uri.fsPath};
}
test('all reported source panes contribute, background tabs only supply context',()=>{
  const f=fixture(),inputs=visibleInputs(f.api,f.relative);
  assert.deepEqual(inputs.map(v=>[v.path,v.active,v.ranges]),[['a.py',true,[[1,2]]],['b.py',false,[[1,2]]]]);
  assert.deepEqual(openTabs(f.api,f.relative),['a.py','c.py','b.py']);
  assert.deepEqual(f.reads,['a.py','b.py']);
});
test('an empty visible list never falls back to the last active editor',()=>{
  const f=fixture();f.api.window.visibleTextEditors=[];
  assert.deepEqual(visibleInputs(f.api,f.relative),[]);assert.deepEqual(f.reads,[]);
});
test('diff and unsupported active tabs are excluded before reading contents',()=>{
  const f=fixture();f.api.window.tabGroups.all[1].activeTab={input:{original:{fsPath:'x.py'},modified:{fsPath:'b.py'}}};
  assert.deepEqual(visibleInputs(f.api,f.relative).map(v=>v.path),['a.py']);assert.deepEqual(f.reads,['a.py']);
});
