export interface ToolRun {id:number;message_id:number;tool_call_id:string;tool_name:string;status:string;duration_ms:number|null;input_summary:string|null;output_summary:string|null;error_code:number|null;created_at:string;completed_at:string|null}
export interface Message {id:number;role:string;content:string;status:string;request_id:string;created_at:string;updated_at:string;tool_runs:ToolRun[]}
export interface Conversation {id:number;title:string;status:string;created_at:string;updated_at:string}
export interface ConversationDetail extends Conversation {messages:Message[]}
export interface ConversationList {items:Conversation[];total:number;page:number;page_size:number}
export interface StreamEvent {event:string;data:Record<string,unknown>}
