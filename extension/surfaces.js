'use strict';
// Pane membership is API evidence, never an attention or pixel-occlusion claim.
function plainText(api,input) {
  if(typeof api.TabInputText==='function')return input instanceof api.TabInputText;
  return !!input?.uri&&!input.original&&!input.modified;
}
function visibleInputs(api,relative) {
  const editors=api.window.visibleTextEditors;
  const reported=Array.isArray(editors),groups=api.window.tabGroups?.all||[];
  const candidates=reported?editors:[api.window.activeTextEditor].filter(Boolean);
  return candidates.slice(0,16).flatMap((editor,index)=>{
    const name=relative(editor.document.uri);
    if(!name)return [];
    const group=groups.find(g=>g.viewColumn===editor.viewColumn);
    if(groups.length&&(!group||!plainText(api,group.activeTab?.input)||group.activeTab.input.uri.fsPath!==editor.document.uri.fsPath))return [];
    const ranges=editor.visibleRanges.map(r=>[r.start.line+1,Math.min(editor.document.lineCount,r.end.line+(r.end.character>0?1:0))]).filter(r=>r[1]>=r[0]);
    if(!ranges.length)return [];
    return [{path:name,text:editor.document.getText(),dirty:editor.document.isDirty,documentVersion:editor.document.version,focused:api.window.state.focused,ranges,paneId:'column-'+(editor.viewColumn??index),active:editor===api.window.activeTextEditor,exposure:reported?'reported-visible':'active-fallback'}];
  });
}
function openTabs(api,relative) {
  const groups=api.window.tabGroups?.all;
  if(!groups)return [];
  return [...new Set(groups.flatMap(g=>g.tabs).filter(tab=>plainText(api,tab.input)).map(tab=>relative(tab.input.uri)).filter(Boolean))].slice(0,500);
}
module.exports={visibleInputs,openTabs};
