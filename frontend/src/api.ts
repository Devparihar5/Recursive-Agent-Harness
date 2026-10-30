export type Row = Record<string, any>;
export async function api(path:string, body?:unknown, method?:string):Promise<any>{const response=await fetch('/api'+path,{method:method||(body===undefined?'GET':'POST'),headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok){let message;try {const data=await response.json();message=data.detail||data.error;}catch{message=response.statusText;}throw new Error(typeof message==='string'?message:JSON.stringify(message));}return response.json();}
export function rows(value:any):Row[]{if(Array.isArray(value))return value;return value?.items||value?.tasks||value?.runs||value?.entries||value?.harnesses||value?.models||value?.results||[];}
export function label(row:Row){return row.description||row.name||row.task_id||row.run_id||row.id||'Untitled';}
export function id(row:Row){return row.execution_id||row.run_id||row.task_id||row.entry_id||row.id||row.version||'';}
