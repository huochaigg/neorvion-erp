export interface ToolRun {id:number;message_id:number;tool_call_id:string;tool_name:string;status:string;duration_ms:number|null;input_summary:string|null;output_summary:string|null;error_code:number|null;created_at:string;completed_at:string|null}
export interface Evidence {citation_id:string;source_type:'ERP'|'KNOWLEDGE';resource_type:string;resource_id:string|null;knowledge_base_id:number|null;document_id:number|null;chunk_id:number|null;title:string;excerpt:string|null;source_version:number|null;metadata:Record<string,unknown>;observed_at:string;access_status:'ACTIVE'|'STALE'|'FORBIDDEN'|'MISSING'|'UNAVAILABLE'}
export interface Message {id:number;role:string;content:string;status:string;request_id:string;created_at:string;updated_at:string;tool_runs:ToolRun[];evidences:Evidence[];analysis_status?:string}
export interface Conversation {id:number;title:string;status:string;created_at:string;updated_at:string}
export interface ConversationDetail extends Conversation {messages:Message[]}
export interface ConversationList {items:Conversation[];total:number;page:number;page_size:number}
export interface StreamEvent {event:string;data:Record<string,unknown>}
